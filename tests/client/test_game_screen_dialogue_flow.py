# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""GameScreen dialogue and notification-flow contract tests.

Test oracle (desired outcomes):
- Notifications are queued in FIFO order when a dialogue is already open.
- Dequeued notifications produce dialogues in the same order they were queued.
- Opponent-turn summary is converted into a stable "Your Turn" dialogue payload.
- Opponent-turn summary state is cleared after being consumed.
- Dialogue acknowledgement ("ok") advances to the next queued notification.
"""

from types import SimpleNamespace


def _game_screen_class():
    from game.screens.game_screen import GameScreen

    return GameScreen


class _DummyDialogueBox:
    def __init__(self, response):
        self._response = response

    def update(self, events):
        return self._response


class _DummyGame(SimpleNamespace):
    def update_from_dict(self, data):
        self.updated_with = data
        for key, value in data.items():
            setattr(self, key, value)


def _make_conquer_game_screen():
    GameScreen = _game_screen_class()
    game_screen = GameScreen.__new__(GameScreen)
    game_screen.window = object()
    game_screen.state = SimpleNamespace(
        game=_DummyGame(
            game_id=1,
            player_id=10,
            mode='conquer',
            invader=True,
            player_name='Attacker',
            opponent_name='Defender',
            game_over=False,
            conquer_result=None,
            pending_game_over=False,
        )
    )
    game_screen._conquer_result_dialogue_shown = False
    game_screen._reset_battle_state = lambda: None
    notifications = []
    game_screen.queue_or_show_notification = notifications.append
    return GameScreen, game_screen, notifications


class TestGameScreenDialogueFlow:
    def test_notification_queue_order_is_preserved(self):
        GameScreen = _game_screen_class()
        game_screen = GameScreen.__new__(GameScreen)
        game_screen.dialogue_box = object()
        game_screen.pending_notifications = []
        game_screen._active_dialogue_type = None

        shown_dialogues = []

        def fake_make_dialogue_box(**kwargs):
            shown_dialogues.append(kwargs)
            game_screen.dialogue_box = object()

        game_screen.make_dialogue_box = fake_make_dialogue_box

        GameScreen.queue_or_show_notification(
            game_screen,
            {
                'title': 'First',
                'message': 'First notification',
                'actions': ['ok'],
                'type': 'first_type',
            },
        )
        GameScreen.queue_or_show_notification(
            game_screen,
            {
                'title': 'Second',
                'message': 'Second notification',
                'actions': ['ok'],
                'type': 'second_type',
            },
        )

        assert len(game_screen.pending_notifications) == 2

        game_screen.dialogue_box = None
        GameScreen.show_next_queued_notification(game_screen)
        assert shown_dialogues[0]['title'] == 'First'
        assert game_screen._active_dialogue_type == 'first_type'

        game_screen.dialogue_box = None
        GameScreen.show_next_queued_notification(game_screen)
        assert shown_dialogues[1]['title'] == 'Second'
        assert game_screen._active_dialogue_type == 'second_type'

        game_screen.dialogue_box = None
        GameScreen.show_next_queued_notification(game_screen)
        assert len(shown_dialogues) == 2

    def test_opponent_turn_summary_builds_turn_dialogue_payload(self):
        GameScreen = _game_screen_class()
        game_screen = GameScreen.__new__(GameScreen)
        game_screen.subscreens = {}
        game_screen.state = SimpleNamespace(
            game=SimpleNamespace(
                pending_opponent_turn_summary={
                    'opponent_name': 'Rival',
                    'action': {
                        'type': 'build',
                        'message': 'Rival built a figure',
                    },
                },
                game_over=False,
                pending_game_over=False,
            )
        )

        captured_notifications = []

        def capture_notification(notification):
            captured_notifications.append(notification)

        game_screen.queue_or_show_notification = capture_notification

        GameScreen.check_opponent_turn_notification(game_screen)

        assert len(captured_notifications) == 1
        payload = captured_notifications[0]
        assert payload['title'] == 'Your Turn'
        assert payload['message'] == "Rival's turn:"
        assert 'Rival built a figure' in payload['message_after_images']
        assert "It's your turn now!" in payload['message_after_images']
        assert game_screen.state.game.pending_opponent_turn_summary is None

    def test_acknowledgement_advances_to_next_queued_dialogue(self):
        GameScreen = _game_screen_class()
        game_screen = GameScreen.__new__(GameScreen)
        game_screen.state = SimpleNamespace(game=None)
        game_screen.dialogue_box = _DummyDialogueBox('ok')
        game_screen._active_dialogue_type = None
        game_screen.pending_notifications = [
            {
                'title': 'Queued',
                'message': 'Queued follow-up message',
                'actions': ['ok'],
                'type': 'queued_type',
            }
        ]

        shown_dialogues = []

        def fake_make_dialogue_box(**kwargs):
            shown_dialogues.append(kwargs)
            game_screen.dialogue_box = object()

        game_screen.make_dialogue_box = fake_make_dialogue_box

        GameScreen.handle_events(game_screen, [])

        assert shown_dialogues, 'Expected queued notification to be shown after acknowledgement'
        assert shown_dialogues[0]['title'] == 'Queued'
        assert game_screen._active_dialogue_type == 'queued_type'

    def test_duel_game_over_acknowledgement_opens_rewards_without_model_flag(self):
        GameScreen = _game_screen_class()
        game_screen = GameScreen.__new__(GameScreen)
        pending = {
            'winner_player_id': 1,
            'loser_player_id': 2,
            'loser_rewards': {'gold': 80},
        }
        game_screen.state = SimpleNamespace(
            game=_DummyGame(
                mode='duel',
                player_id=2,
                game_over=False,
                pending_game_over=pending,
                infinite_hammer_active=False,
            )
        )
        game_screen.dialogue_box = _DummyDialogueBox('ok')
        game_screen._active_dialogue_type = 'game_over'
        game_screen.pending_notifications = []
        game_screen._ensure_duel_screen_game = lambda: True

        reward_payloads = []

        def capture_rewards(payload):
            reward_payloads.append(payload)
            game_screen.dialogue_box = object()
            game_screen._active_dialogue_type = 'game_over_rewards'

        game_screen._show_game_over_rewards_dialogue = capture_rewards
        game_screen._on_game_over_acknowledged = lambda: (_ for _ in ()).throw(
            AssertionError('Game-over result should open rewards before navigating')
        )
        game_screen.show_next_queued_notification = lambda: (_ for _ in ()).throw(
            AssertionError('Game-over result should not fall through to generic dialogue handling')
        )

        GameScreen.handle_events(game_screen, [])

        assert reward_payloads == [pending]
        assert game_screen._active_dialogue_type == 'game_over_rewards'

    def test_finished_duel_with_pending_rewards_is_not_suppressed(self):
        GameScreen = _game_screen_class()
        game_screen = GameScreen.__new__(GameScreen)
        pending = {'winner_player_id': 1, 'loser_player_id': 2}
        game = _DummyGame(
            game_id=7,
            player_id=2,
            mode='duel',
            game_over=True,
            game_over_shown=False,
            pending_game_over=pending,
            cached_figures_data={2: [object()]},
            players=[{'id': 2}],
            _figures_data_version=0,
        )
        game_screen.state = SimpleNamespace(game=game, subscreen='field')
        game_screen._current_game_key = (7, 2)
        game_screen.previous_subscreen = 'field'
        game_screen.subscreens = {}
        game_screen.display_elements = []
        game_screen.main_hand = SimpleNamespace(update=lambda _game: None, deselect_all_cards=lambda: None)
        game_screen.side_hand = SimpleNamespace(update=lambda _game: None, deselect_all_cards=lambda: None)
        game_screen._try_handle_finished_conquer_game = lambda: False
        game_screen.check_conquer_battle_ended = lambda: None

        checked = []
        game_screen.check_game_over = lambda: checked.append(True)

        GameScreen.update_game(game_screen)

        assert checked == [True]
        assert game.game_over_shown is False

    def test_finished_duel_waits_for_battle_dialogue_before_rewards(self):
        GameScreen = _game_screen_class()
        game_screen = GameScreen.__new__(GameScreen)
        game = _DummyGame(
            game_id=7,
            player_id=2,
            mode='duel',
            game_over=True,
            game_over_shown=False,
            pending_game_over={'winner_player_id': 1, 'loser_player_id': 2},
            cached_figures_data={2: [object()]},
            players=[{'id': 2}],
            _figures_data_version=0,
        )
        game_screen.state = SimpleNamespace(game=game, subscreen='battle')
        game_screen._current_game_key = (7, 2)
        game_screen.previous_subscreen = 'battle'
        game_screen.subscreens = {'battle': SimpleNamespace(dialogue_box=object())}
        game_screen.display_elements = []
        game_screen.main_hand = SimpleNamespace(update=lambda _game: None, deselect_all_cards=lambda: None)
        game_screen.side_hand = SimpleNamespace(update=lambda _game: None, deselect_all_cards=lambda: None)
        game_screen._try_handle_finished_conquer_game = lambda: False
        game_screen.check_conquer_battle_ended = lambda: None
        game_screen.check_game_over = lambda: (_ for _ in ()).throw(
            AssertionError('Game-over dialogue should wait for the battle result dialogue')
        )

        GameScreen.update_game(game_screen)

        assert game.game_over_shown is False

    def test_conquer_game_start_pending_prelude_target_sets_selection_state(self):
        GameScreen = _game_screen_class()
        game_screen = GameScreen.__new__(GameScreen)
        game_screen.subscreens = {}
        game_screen._get_spell_icon_image = lambda _name: []

        game_screen.state = SimpleNamespace(
            pending_conquer_prelude_target=None,
            game=SimpleNamespace(
                pending_opponent_turn_summary={
                    'action': 'game_start',
                    'mode': 'conquer',
                    'opponent_name': 'Rival',
                    'is_turn': True,
                    'is_invader': True,
                    'own_prelude_spells': [],
                    'own_drawn_cards': [],
                    'opponent_prelude_spells': [],
                    'own_prelude_no_target_spells': [],
                    'opponent_prelude_no_target_spells': [],
                    'pending_prelude_target': {
                        'spell_id': 99,
                        'spell_name': 'Poison',
                        'target_scope': 'opponent',
                        'valid_target_ids': [1, 2],
                    },
                    'battle_modifier': [],
                },
                game_over=False,
                pending_game_over=False,
                _game_start_pending=True,
                land_tier=1,
                pending_conquer_prelude_target=False,
            ),
        )

        captured_notifications = []
        game_screen.queue_or_show_notification = captured_notifications.append

        GameScreen.check_opponent_turn_notification(game_screen)

        assert game_screen.state.pending_conquer_prelude_target is not None
        assert game_screen.state.game.pending_conquer_prelude_target is True
        assert game_screen.state.pending_conquer_prelude_target['spell_name'] == 'Poison'
        assert any(n.get('title') == 'Select Prelude Target' for n in captured_notifications)
        assert game_screen.state.game.pending_opponent_turn_summary is None

    def test_conquer_game_start_no_valid_target_shows_explicit_dialog(self):
        GameScreen = _game_screen_class()
        game_screen = GameScreen.__new__(GameScreen)
        game_screen.subscreens = {}
        game_screen._get_spell_icon_image = lambda _name: []

        game_screen.state = SimpleNamespace(
            pending_conquer_prelude_target=None,
            game=SimpleNamespace(
                pending_opponent_turn_summary={
                    'action': 'game_start',
                    'mode': 'conquer',
                    'opponent_name': 'Rival',
                    'is_turn': True,
                    'is_invader': True,
                    'own_prelude_spells': [],
                    'own_drawn_cards': [],
                    'opponent_prelude_spells': [],
                    'own_prelude_no_target_spells': [{'spell_name': 'Poison'}],
                    'opponent_prelude_no_target_spells': [],
                    'pending_prelude_target': None,
                    'battle_modifier': [],
                },
                game_over=False,
                pending_game_over=False,
                _game_start_pending=True,
                land_tier=1,
                pending_conquer_prelude_target=False,
            ),
        )

        captured_notifications = []
        game_screen.queue_or_show_notification = captured_notifications.append

        GameScreen.check_opponent_turn_notification(game_screen)

        no_target_payloads = [n for n in captured_notifications if n.get('title') == 'No Valid Target']
        assert len(no_target_payloads) == 1
        assert 'No valid target was available' in no_target_payloads[0]['message']

    def test_conquer_game_start_modifier_messages_include_effect_explanations(self):
        GameScreen = _game_screen_class()
        game_screen = GameScreen.__new__(GameScreen)
        game_screen.subscreens = {}
        game_screen._get_spell_icon_image = lambda _name: []
        game_screen._previous_battle_modifiers = []
        game_screen._seen_conquer_opponent_spell_ids = set()

        battle_modifier = [
            {'type': 'Blitzkrieg', 'caster_id': 1},
            {'type': 'Civil War', 'caster_id': 2},
        ]

        game_screen.state = SimpleNamespace(
            pending_conquer_prelude_target=None,
            game=SimpleNamespace(
                pending_opponent_turn_summary={
                    'action': 'game_start',
                    'mode': 'conquer',
                    'opponent_name': 'Rival',
                    'is_turn': True,
                    'is_invader': True,
                    'own_prelude_spells': [{'spell_name': 'Blitzkrieg'}],
                    'own_drawn_cards': [],
                    'opponent_prelude_spells': [{'spell_name': 'Civil War'}],
                    'own_prelude_no_target_spells': [],
                    'opponent_prelude_no_target_spells': [],
                    'pending_prelude_target': None,
                    'battle_modifier': battle_modifier,
                },
                game_over=False,
                pending_game_over=False,
                _game_start_pending=True,
                land_tier=1,
                pending_conquer_prelude_target=False,
                player_id=1,
                cached_active_spells=[
                    {'id': 44, 'player_id': 2, 'spell_name': 'Civil War'},
                    {'id': 45, 'player_id': 1, 'spell_name': 'Blitzkrieg'},
                ],
            ),
        )

        captured_notifications = []
        game_screen.queue_or_show_notification = captured_notifications.append

        GameScreen.check_opponent_turn_notification(game_screen)

        own_prelude = next(n for n in captured_notifications if n.get('title') == 'Prelude Spell')
        opp_prelude = next(n for n in captured_notifications if n.get('title') == 'Opponent Prelude')

        assert 'Blitzkrieg:' in own_prelude['message']
        assert 'Ceasefire is active until the last turn.' in own_prelude['message']
        assert 'Civil War:' in opp_prelude.get('message_after_images', '')
        assert game_screen._previous_battle_modifiers == battle_modifier
        assert game_screen._seen_conquer_opponent_spell_ids == {44}

    def test_conquer_battle_modifier_changes_are_suppressed(self):
        GameScreen = _game_screen_class()
        game_screen = GameScreen.__new__(GameScreen)
        game_screen._previous_battle_modifiers = []

        game_screen.state = SimpleNamespace(
            game=SimpleNamespace(
                mode='conquer',
                battle_modifier=[{'type': 'Peasant War', 'caster_id': 2}],
                suppress_next_turn_summary=False,
                player_id=1,
            )
        )

        captured_notifications = []
        game_screen.queue_or_show_notification = captured_notifications.append

        GameScreen.check_battle_modifier_changes(game_screen)

        assert captured_notifications == []
        assert game_screen._previous_battle_modifiers == [{'type': 'Peasant War', 'caster_id': 2}]

    def test_conquer_battle_ready_shows_hidden_counter_advance_summary(self):
        GameScreen = _game_screen_class()
        game_screen = GameScreen.__new__(GameScreen)

        class _HiddenSurface:
            def copy(self):
                return self

        hidden_surface = _HiddenSurface()
        defender_figure = SimpleNamespace(
            id=200,
            name='Secret Defender',
            family=SimpleNamespace(field='village'),
            cards=[1, 2, 3],
        )

        game_screen.subscreens = {
            'field': SimpleNamespace(
                figures=[defender_figure],
                figure_icons=[SimpleNamespace(figure=defender_figure, frame_hidden_img=hidden_surface)],
            )
        }
        game_screen.dialogue_box = None
        game_screen._seen_conquer_opponent_spell_ids = {77}
        game_screen._get_spell_icon_image = lambda _name: []

        captured_notifications = []
        submitted_decisions = []
        game_screen.queue_or_show_notification = captured_notifications.append
        game_screen._submit_battle_decision = submitted_decisions.append

        game_screen.state = SimpleNamespace(
            game=SimpleNamespace(
                pending_battle_ready=True,
                battle_ready_shown=False,
                advancing_figure_id=101,
                defending_figure_id=200,
                advancing_player_id=1,
                player_id=1,
                mode='conquer',
                battle_confirmed=False,
                battle_decisions={},
                battle_modifier=[],
                cached_active_spells=[{'id': 77, 'player_id': 2, 'spell_name': 'Civil War'}],
                opponent_name='Rival',
            )
        )

        GameScreen.check_battle_ready(game_screen)

        assert len(captured_notifications) == 1
        payload = captured_notifications[0]
        assert payload['title'] == 'Defender Response'
        assert 'hidden Village figure with 3 cards' in payload['message']
        assert 'Secret Defender' not in payload['message']
        assert payload['images'] == [hidden_surface]
        assert submitted_decisions == ['battle']
        assert game_screen.state.game.pending_battle_ready is False

    def test_conquer_counter_spell_notification_includes_modifier_effect_text(self):
        GameScreen = _game_screen_class()
        game_screen = GameScreen.__new__(GameScreen)
        game_screen.dialogue_box = None
        game_screen._seen_conquer_opponent_spell_ids = set()
        game_screen._get_spell_icon_image = lambda _name: []

        advancing_figure = SimpleNamespace(
            id=101,
            name='Attacker',
            family=SimpleNamespace(field='military'),
            cards=[1, 2],
        )
        game_screen.subscreens = {
            'field': SimpleNamespace(
                figures=[advancing_figure],
                figure_icons=[SimpleNamespace(figure=advancing_figure)],
            )
        }

        captured_notifications = []
        submitted_decisions = []
        game_screen.queue_or_show_notification = captured_notifications.append
        game_screen._submit_battle_decision = submitted_decisions.append

        game_screen.state = SimpleNamespace(
            game=SimpleNamespace(
                pending_battle_ready=True,
                battle_ready_shown=False,
                advancing_figure_id=101,
                defending_figure_id=None,
                advancing_player_id=1,
                player_id=1,
                mode='conquer',
                battle_confirmed=False,
                battle_decisions={},
                battle_modifier=[],
                cached_active_spells=[{'id': 88, 'player_id': 2, 'spell_name': 'Blitzkrieg'}],
                opponent_name='Rival',
            )
        )

        GameScreen.check_battle_ready(game_screen)

        counter_payload = next(n for n in captured_notifications if n.get('title') == 'Defender Counter Spell')
        msg_after = counter_payload.get('message_after_images', '')
        assert 'Blitzkrieg:' in msg_after
        assert 'Ceasefire is active until the last turn.' in msg_after
        assert submitted_decisions == ['battle']

    def test_conquer_defender_waits_for_invader_battle_decision(self):
        GameScreen = _game_screen_class()
        game_screen = GameScreen.__new__(GameScreen)
        game_screen.dialogue_box = None

        submitted_decisions = []
        game_screen._submit_battle_decision = submitted_decisions.append
        game_screen.state = SimpleNamespace(
            game=SimpleNamespace(
                pending_battle_ready=True,
                battle_ready_shown=False,
                advancing_figure_id=201,
                defending_figure_id=101,
                advancing_player_id=20,
                player_id=10,
                mode='conquer',
                battle_confirmed=False,
                battle_decisions={},
            )
        )

        GameScreen.check_battle_ready(game_screen)

        assert submitted_decisions == []
        assert game_screen.state.game.pending_battle_ready is False
        assert game_screen.state.game.battle_ready_shown is False

    def test_conquer_defender_submits_after_invader_battle_decision(self):
        GameScreen = _game_screen_class()
        game_screen = GameScreen.__new__(GameScreen)
        game_screen.dialogue_box = None

        submitted_decisions = []
        game_screen._submit_battle_decision = submitted_decisions.append
        game_screen.state = SimpleNamespace(
            game=SimpleNamespace(
                pending_battle_ready=True,
                battle_ready_shown=False,
                advancing_figure_id=201,
                defending_figure_id=101,
                advancing_player_id=20,
                player_id=10,
                mode='conquer',
                battle_confirmed=False,
                battle_decisions={'20': 'battle'},
            )
        )

        GameScreen.check_battle_ready(game_screen)

        assert submitted_decisions == ['battle']
        assert game_screen.state.game.pending_battle_ready is False

    def test_conquer_result_uses_original_attacker_after_invader_swap(self):
        GameScreen, game_screen, notifications = _make_conquer_game_screen()
        game_screen.state.game.invader = False
        game_screen.state.game.last_battle_result = {
            'conquer_attacker_player_id': 10,
            'conquer_defender_player_id': 20,
        }

        handled = GameScreen._handle_conquer_result_response(game_screen, {
            'success': True,
            'conquer_result': 'attacker_won',
            'attacker_won': True,
            'land_tier': 2,
        })

        assert handled is True
        assert len(notifications) == 1
        assert notifications[0]['title'] == 'Land Conquered!'

    def test_conquer_result_gain_notification_uses_loot_card_images(self, monkeypatch):
        GameScreen, game_screen, notifications = _make_conquer_game_screen()

        class _DummyCardImg:
            def __init__(self, _window, suit, rank):
                self.front_img = f'{rank}-{suit}'

        monkeypatch.setattr('game.components.cards.card_img.CardImg', _DummyCardImg)

        handled = GameScreen._handle_conquer_result_response(game_screen, {
            'success': True,
            'conquer_result': 'attacker_won',
            'attacker_won': True,
            'land_tier': 2,
            'loot_gained_cards': [
                {'suit': 'Hearts', 'rank': 'K'},
                {'suit': 'Spades', 'rank': '8'},
            ],
        })

        assert handled is True
        payload = notifications[0]
        assert payload['title'] == 'Land Conquered!'
        assert payload['message'].endswith('Loot gained (pending collection):')
        assert 'K of Hearts' not in payload['message']
        assert payload['images'] == ['K-Hearts', '8-Spades']
        assert 'Collect looted cards from the Loot Inbox' in payload['message_after_images']

    def test_conquer_result_loss_notification_uses_loot_card_images(self, monkeypatch):
        GameScreen, game_screen, notifications = _make_conquer_game_screen()

        class _DummyCardImg:
            def __init__(self, _window, suit, rank):
                self.front_img = f'{rank}-{suit}'

        monkeypatch.setattr('game.components.cards.card_img.CardImg', _DummyCardImg)

        handled = GameScreen._handle_conquer_result_response(game_screen, {
            'success': True,
            'conquer_result': 'defender_won',
            'attacker_won': False,
            'loot_lost_cards': [
                {'suit': 'Clubs', 'rank': '4'},
            ],
        })

        assert handled is True
        payload = notifications[0]
        assert payload['title'] == 'Attack Failed'
        assert payload['message'].endswith('Cards looted by defending kingdom:')
        assert '4 of Clubs' not in payload['message']
        assert payload['images'] == ['4-Clubs']
        assert 'Every unlooted attack card returned to your collection.' in payload['message_after_images']

    def test_cannot_advance_conquer_result_routes_to_game_over_notification(self, monkeypatch):
        GameScreen, game_screen, notifications = _make_conquer_game_screen()

        result = {
            'success': True,
            'conquer_result': 'defender_won',
            'attacker_won': False,
            'auto_loss_reason': 'no_figures_to_advance',
            'land': {'col': 4, 'row': 5},
            'game': {'state': 'finished', 'winner_player_id': 20},
        }
        monkeypatch.setattr('utils.game_service.cannot_advance_loss', lambda *_args: result)

        GameScreen._handle_cannot_advance_loss(game_screen)

        assert game_screen.state.game.game_over is True
        assert game_screen.state.game.conquer_result == 'defender_won'
        assert len(notifications) == 1
        payload = notifications[0]
        assert payload['type'] == 'game_over'
        assert payload['title'] == 'Attack Failed'
        assert 'No figure could legally advance' in payload['message']

    def test_defender_no_figures_conquer_result_routes_to_game_over_notification(self, monkeypatch):
        GameScreen, game_screen, notifications = _make_conquer_game_screen()

        result = {
            'success': True,
            'conquer_result': 'attacker_won',
            'attacker_won': True,
            'auto_loss_reason': 'no_defender_figures',
            'land': {'col': 6, 'row': 7},
            'game': {'state': 'finished', 'winner_player_id': 10},
        }
        monkeypatch.setattr('utils.game_service.defender_no_figures_loss', lambda *_args: result)

        GameScreen._handle_defender_no_figures_loss(game_screen)

        assert game_screen.state.game.game_over is True
        assert game_screen.state.game.conquer_result == 'attacker_won'
        assert len(notifications) == 1
        payload = notifications[0]
        assert payload['type'] == 'game_over'
        assert payload['title'] == 'Land Conquered!'
        assert 'The defender had no legal battle figure' in payload['message']

    def test_finished_conquer_game_poll_derives_result_once(self):
        GameScreen, game_screen, notifications = _make_conquer_game_screen()
        game_screen.state.game.state = 'finished'
        game_screen.state.game.winner_player_id = 20
        game_screen.state.game.last_battle_result = {
            'conquer_attacker_player_id': 10,
            'conquer_defender_player_id': 20,
            'auto_loss_reason': 'no_figures_to_advance',
        }

        handled = GameScreen._try_handle_finished_conquer_game(game_screen)
        handled_again = GameScreen._try_handle_finished_conquer_game(game_screen)

        assert handled is True
        assert handled_again is True
        assert game_screen.state.game.conquer_result == 'defender_won'
        assert len(notifications) == 1
        assert notifications[0]['title'] == 'Attack Failed'

    def test_defender_selectable_precheck_allows_checkmate_fallback(self):
        GameScreen, game_screen, _notifications = _make_conquer_game_screen()
        only_defender = SimpleNamespace(
            id=200,
            player_id=20,
            checkmate=True,
            family=SimpleNamespace(field='village'),
        )
        game_screen.state.game.advancing_figure_id = None
        game_screen.state.game.battle_modifier = []
        game_screen.subscreens = {
            'field': SimpleNamespace(
                categorized_figures={'opponent': {'village': [only_defender]}},
                figures=[only_defender],
            )
        }

        assert GameScreen._check_any_defender_selectable(game_screen) is True
