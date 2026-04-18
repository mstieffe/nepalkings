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