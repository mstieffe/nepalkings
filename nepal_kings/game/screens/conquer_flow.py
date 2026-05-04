# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Presentation helpers for the conquer-mode flow.

This module deliberately reads state only.  It does not submit actions or
mutate game objects, which keeps the redesigned conquer UI separate from the
existing battle rules.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence, Tuple


CONQUER_PHASES: Tuple[Tuple[str, str], ...] = (
    ('start', 'Start'),
    ('prelude', 'Prelude'),
    ('advance', 'Advance'),
    ('defender', 'Defender'),
    ('moves', 'Moves'),
    ('battle', 'Battle'),
    ('result', 'Result'),
)


@dataclass(frozen=True)
class ConquerObjective:
    phase: str
    headline: str
    instruction: str = ''
    target_tab: Optional[str] = None
    primary_action: Optional[str] = None
    waiting: bool = False
    tone: str = 'neutral'


@dataclass(frozen=True)
class ConquerEvent:
    key: str
    phase: str
    title: str
    detail: str = ''
    tone: str = 'info'
    spell_names: Tuple[str, ...] = field(default_factory=tuple)
    order: int = 0
    spell_side: str = ''  # 'own', 'opponent', or '' if not relevant
    # 'spell_role' helps the panel separate the prelude icon from the counter
    # icon when the same side cast both during a single conquer cycle.
    spell_role: str = ''  # 'prelude', 'counter', '' if unknown


def event_spells_by_side(events: Iterable[ConquerEvent]) -> dict:
    """Group spell names by side, preserving first-seen order.

    Returns a mapping ``{'own': [...], 'opponent': [...]}``.  Each side
    further keeps role hints in a parallel list so callers can render
    prelude/counter icons distinctly.
    """
    buckets = {'own': [], 'opponent': []}
    seen = {'own': set(), 'opponent': set()}
    roles = {'own': {}, 'opponent': {}}
    for event in events:
        side = event.spell_side
        if side not in ('own', 'opponent'):
            continue
        for name in event.spell_names:
            if not name:
                continue
            if name not in seen[side]:
                seen[side].add(name)
                buckets[side].append(name)
                roles[side][name] = event.spell_role or ''
            elif event.spell_role and not roles[side].get(name):
                roles[side][name] = event.spell_role
    return {'own': list(buckets['own']),
            'opponent': list(buckets['opponent']),
            'own_roles': dict(roles['own']),
            'opponent_roles': dict(roles['opponent'])}


def infer_spell_metadata(data: dict) -> Tuple[str, str]:
    """Infer ``(spell_side, spell_role)`` from a notification payload.

    Reads existing fields; falls back to event_key prefixes and titles so
    callers don't have to retro-fit every notification site.
    """
    side = (data.get('spell_side') or '').lower()
    role = (data.get('spell_role') or '').lower()

    key = (data.get('event_key') or '').lower()
    title = (data.get('title') or '').lower()

    if not side:
        if key.startswith('own_') or key.startswith('caster_') or key.startswith('prelude_target:'):
            side = 'own'
        elif key.startswith('opponent_') or key.startswith('defender_counter'):
            side = 'opponent'
        elif title.startswith('opponent ') or title.startswith("opponent's "):
            side = 'opponent'
        elif 'your prelude' in title or title.startswith('prelude') or title.startswith('your ') or title.startswith('select prelude'):
            side = 'own'

    if not role:
        if 'counter' in key or 'counter' in title:
            role = 'counter'
        elif 'prelude' in key or 'prelude' in title:
            role = 'prelude'
        elif data.get('phase') == 'prelude':
            role = 'prelude'

    return side, role


def _get(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default) if obj is not None else default


def _pending_prelude_target(game: Any, state: Any = None) -> Any:
    return _get(state, 'pending_conquer_prelude_target') or (
        _get(game, 'pending_conquer_prelude_target', False)
    )


def _has_modifier(game: Any, modifier_name: str) -> bool:
    modifiers = _get(game, 'battle_modifier', [])
    if not isinstance(modifiers, list):
        return False
    return any(
        isinstance(mod, dict) and mod.get('type') == modifier_name
        for mod in modifiers
    )


def _figure_name(figure: Any, fallback: str) -> str:
    return _get(figure, 'name', fallback) or fallback


def _pending_confirmation_objective(field_screen: Any) -> Optional[ConquerObjective]:
    if not field_screen:
        return None

    advance = _get(field_screen, '_pending_advance_figure')
    if advance:
        name = _figure_name(advance, 'this figure')
        return ConquerObjective(
            phase='advance',
            headline=f'Advance {name}?',
            instruction='Confirm the advancing figure in the command panel.',
            target_tab='field',
            primary_action='confirm_figure',
            tone='action',
        )

    defender = _get(field_screen, 'figure_pending_defender_selection')
    if defender:
        name = _figure_name(defender, 'this figure')
        return ConquerObjective(
            phase='defender',
            headline=f'Select {name} as defender?',
            instruction='Confirm the opponent figure that will face your advance.',
            target_tab='field',
            primary_action='confirm_figure',
            tone='action',
        )

    own_defender = _get(field_screen, 'figure_pending_own_defender_selection')
    if own_defender:
        name = _figure_name(own_defender, 'this figure')
        return ConquerObjective(
            phase='defender',
            headline=f'Defend with {name}?',
            instruction='Confirm your own defender for the Invader Swap battle.',
            target_tab='field',
            primary_action='confirm_figure',
            tone='action',
        )

    return None


def derive_conquer_objective(game: Any, state: Any = None,
                             field_screen: Any = None,
                             battle_shop_screen: Any = None) -> ConquerObjective:
    """Return the single most useful instruction for the current conquer state."""
    if not game:
        return ConquerObjective('start', 'Loading conquer battle',
                                'Waiting for battle state.', waiting=True)

    pending_confirmation = _pending_confirmation_objective(field_screen)
    if pending_confirmation:
        return pending_confirmation

    if _get(game, 'game_over', False) or _get(game, 'pending_game_over', False):
        return ConquerObjective(
            phase='result',
            headline='Conquer result ready',
            instruction='Review the battle result.',
            waiting=True,
            tone='result',
        )

    pending_target = _pending_prelude_target(game, state)
    if pending_target:
        spell_name = 'Prelude spell'
        target_scope = None
        if isinstance(pending_target, dict):
            spell_name = pending_target.get('spell_name') or spell_name
            target_scope = pending_target.get('target_scope')
        target = 'one of your figures' if target_scope == 'own' else "one of the defender's figures"
        return ConquerObjective(
            phase='prelude',
            headline=f'Resolve {spell_name}',
            instruction=f'Select {target} on the field.',
            target_tab='field',
            primary_action='select_target',
            tone='action',
        )

    if (_get(game, 'pending_forced_advance', False)
            and not _get(game, 'advancing_figure_id')):
        return ConquerObjective(
            phase='advance',
            headline='Choose your battle figure',
            instruction='Select one of your legal figures on the field to advance.',
            target_tab='field',
            primary_action='select_advance',
            tone='action',
        )

    if _get(game, 'civil_war_awaiting_second', False):
        return ConquerObjective(
            phase='advance',
            headline='Civil War: optional second attacker',
            instruction='Select a second same-color village figure, or skip the second figure.',
            target_tab='field',
            primary_action='select_second',
            tone='action',
        )

    if _get(game, 'civil_war_defender_second', False):
        own_mode = bool(_get(field_screen, 'conquer_own_defender_mode', False))
        return ConquerObjective(
            phase='defender',
            headline='Civil War: optional second defender',
            instruction=('Select a second same-color own village figure.'
                         if own_mode else
                         'Select a second same-color opponent village figure.'),
            target_tab='field',
            primary_action='select_second',
            tone='action',
        )

    if (_get(game, 'pending_defender_selection', False)
            and _get(game, 'turn', False)):
        restriction = ''
        if _has_modifier(game, 'Peasant War'):
            restriction = ' Peasant War: village figures only.'
        elif _has_modifier(game, 'Civil War'):
            restriction = ' Civil War: village figures only.'
        return ConquerObjective(
            phase='defender',
            headline="Choose the defender's battle figure",
            instruction=f"Select the opponent figure that will fight your advance.{restriction}",
            target_tab='field',
            primary_action='select_defender',
            tone='action',
        )

    if _get(game, 'pending_conquer_own_defender_selection', False):
        return ConquerObjective(
            phase='defender',
            headline='Invader Swap: choose your defender',
            instruction='Select one of your own legal figures to defend against the invader.',
            target_tab='field',
            primary_action='select_own_defender',
            tone='action',
        )

    advancing_id = _get(game, 'advancing_figure_id')
    defending_id = _get(game, 'defending_figure_id')
    player_id = _get(game, 'player_id')
    advancing_player_id = _get(game, 'advancing_player_id')

    if advancing_id and advancing_player_id == player_id and not _get(game, 'turn', False) and not defending_id:
        return ConquerObjective(
            phase='defender',
            headline='Waiting for defender response',
            instruction='The defender is deciding how the battle figure will be chosen.',
            target_tab='field',
            waiting=True,
            tone='waiting',
        )

    if advancing_id and advancing_player_id != player_id and _get(game, 'turn', False) and not defending_id:
        if _has_modifier(game, 'Blitzkrieg'):
            instruction = 'Blitzkrieg prevents counter-advance. Spend the turn, then the attacker chooses.'
        else:
            instruction = 'Counter-advance with a legal figure or spend the turn normally.'
        return ConquerObjective(
            phase='advance',
            headline='Respond to the enemy advance',
            instruction=instruction,
            target_tab='field',
            primary_action='respond_advance',
            tone='action',
        )

    if _get(game, 'waiting_for_defender_pick_shown', False) and advancing_id and not defending_id:
        return ConquerObjective(
            phase='defender',
            headline='Battle incoming',
            instruction='The attacker is selecting which figure will defend.',
            target_tab='field',
            waiting=True,
            tone='waiting',
        )

    if (_get(game, 'battle_moves_phase', False)
            and not _get(game, 'battle_moves_ready', False)
            and not _get(game, 'waiting_for_opponent_battle_moves', False)):
        count = len(_get(battle_shop_screen, 'bought_moves', []) or [])
        return ConquerObjective(
            phase='moves',
            headline='Confirm battle moves',
            instruction=('Swap committed moves if desired, then press Ready.'
                         if count >= 3 else
                         'Select the remaining battle moves, then press Ready.'),
            target_tab='battle_shop',
            primary_action='ready_moves',
            tone='action',
        )

    if (_get(game, 'waiting_for_opponent_battle_moves', False)
            or (_get(game, 'battle_moves_ready', False)
                and not _get(game, 'both_battle_moves_ready', False))):
        return ConquerObjective(
            phase='moves',
            headline='Waiting for battle moves',
            instruction='Your moves are locked. Waiting for the opponent.',
            target_tab='battle_shop',
            waiting=True,
            tone='waiting',
        )

    if (_get(game, 'both_battle_moves_ready', False)
            or (_get(game, 'battle_confirmed', False)
                and _get(game, 'battle_turn_player_id') is not None)):
        your_turn = _get(game, 'battle_turn_player_id') == player_id
        return ConquerObjective(
            phase='battle',
            headline='Play a battle move' if your_turn else 'Opponent battle move',
            instruction=('Choose a move and confirm it.'
                         if your_turn else
                         'Waiting for the opponent to play.'),
            target_tab='battle',
            primary_action='play_move' if your_turn else None,
            waiting=not your_turn,
            tone='action' if your_turn else 'waiting',
        )

    if _get(game, 'pending_battle_ready', False):
        return ConquerObjective(
            phase='moves',
            headline='Battle figures selected',
            instruction='Conquer battles fight automatically. Preparing battle moves.',
            target_tab='battle_shop',
            waiting=True,
            tone='waiting',
        )

    if _get(game, 'turn', False):
        return ConquerObjective(
            phase='advance',
            headline='Prepare the conquest',
            instruction='Use the field state to decide which figure should advance.',
            target_tab='field',
            tone='neutral',
        )

    return ConquerObjective(
        phase='advance',
        headline='Waiting for opponent',
        instruction='The battle will continue when the opponent acts.',
        target_tab='field',
        waiting=True,
        tone='waiting',
    )


def spell_names_from_events(events: Iterable[ConquerEvent]) -> Tuple[str, ...]:
    """Return spell names in first-seen order for persistent icon display."""
    seen = set()
    names = []
    for event in events:
        for name in event.spell_names:
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return tuple(names)
