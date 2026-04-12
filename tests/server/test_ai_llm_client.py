# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Parser-focused tests for AI LLM client response handling."""

from ai.llm_client import parse_action_response


def test_parse_action_response_accepts_direct_json():
    parsed = parse_action_response('{"action": 2, "plan": "pressure next turn"}')
    assert parsed['action'] == 2
    assert parsed['plan'] == 'pressure next turn'


def test_parse_action_response_accepts_json_code_fence():
    text = """```json
{"action": 4, "plan": "counter and hold"}
```"""
    parsed = parse_action_response(text)
    assert parsed['action'] == 4
    assert parsed['plan'] == 'counter and hold'


def test_parse_action_response_uses_json_object_from_reasoning_text():
    text = (
        "I should preserve tempo first.\n"
        "Then pick the option with safer risk profile.\n"
        "{\"action\": 3, \"plan\": \"force defender mismatch\"}"
    )
    parsed = parse_action_response(text)
    assert parsed['action'] == 3
    assert parsed['plan'] == 'force defender mismatch'


def test_parse_action_response_falls_back_to_action_number_pattern():
    parsed = parse_action_response('Action: 5 because this keeps invader control.')
    assert parsed['action'] == 5


def test_parse_action_response_defaults_to_first_action_when_unparseable():
    parsed = parse_action_response('No valid action number available in this reply.')
    assert parsed['action'] == 1