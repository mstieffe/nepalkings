# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Static contract between client coach ids and server persistence lists."""

import ast
from pathlib import Path


SCREENS = Path(__file__).resolve().parents[2] / 'nepal_kings' / 'game' / 'screens'


def _literal_client_hint_ids():
    ids = set()
    marker_names = {'_mark_menu_coach_seen', '_mark_conquer_battle_coach_seen'}
    for path in SCREENS.glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and 'coach' in node.name:
                for child in ast.walk(node):
                    if not isinstance(child, ast.Dict):
                        continue
                    for key, value in zip(child.keys, child.values):
                        if (isinstance(key, ast.Constant) and key.value == 'id'
                                and isinstance(value, ast.Constant)
                                and isinstance(value.value, str)):
                            ids.add(value.value)
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in marker_names
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                ids.add(node.args[0].value)
    ids.add('loot_risk_intro')
    return ids


def test_literal_client_coach_ids_have_server_persistence_contract():
    from onboarding_service import DUEL_HINT_IDS, MENU_HINT_IDS

    transient = {'kingdom_conquer_retry'}
    persisted = set(DUEL_HINT_IDS) | set(MENU_HINT_IDS)
    missing = _literal_client_hint_ids() - persisted - transient
    assert not missing, f'Client coach ids missing from server whitelist: {sorted(missing)}'
