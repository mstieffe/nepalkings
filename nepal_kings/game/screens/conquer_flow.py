# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Presentation helpers for the conquer-mode flow.

This module deliberately reads state only.  It does not submit actions or
mutate game objects, which keeps the redesigned conquer UI separate from the
existing battle rules.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Tuple


CONQUER_PHASES: Tuple[Tuple[str, str], ...] = (
    ('start', 'Start'),
    ('prelude', 'Prelude'),
    ('advance', 'Advance'),
    ('defender', 'Defender'),
    ('moves', 'Moves'),
    ('battle', 'Battle'),
    ('result', 'Result'),
)


# Timeline step kinds.  Order matters — left-to-right rendering follows it.
TIMELINE_KINDS: Tuple[str, ...] = (
    'overview',
    'prelude_own',
    'prelude_opp',
    'attacker',
    'counter',
    'defender',
    'to_battle',
)


_COUNTER_TIMELINE_MODIFIER_SPELLS = frozenset({'Blitzkrieg'})


@dataclass(frozen=True)
class ConquerObjective:
    phase: str
    headline: str
    instruction: str = ''
    target_tab: Optional[str] = None
    primary_action: Optional[str] = None
    waiting: bool = False
    tone: str = 'neutral'


@dataclass
class TimelineStep:
    """One bubble on the conquer timeline.

    The panel reads this purely as a presentation contract.  ``derive_conquer_
    timeline`` is responsible for filling every field from the live game state.
    """

    kind: str
    title: str
    owner: str = ''            # 'you', '<opponent_name>', or '' for neutral
    icon_kind: str = ''        # 'land' | 'spell' | 'figure' | 'go' | 'none'
    icon_payload: Any = None   # spell_name str, figure obj, etc.
    sub_icons: Tuple[Any, ...] = ()
    completed: bool = False
    active: bool = False
    interactive: bool = False  # requires user click vs auto-advance
    primary_action: Optional[str] = None  # 'confirm' | 'cancel' | 'next' | None
    tone: str = 'neutral'      # 'neutral' | 'action' | 'waiting' | 'good' | 'bad'
    sidenote: str = ''
    info_headline: str = ''
    info_body: str = ''
    info_assets: Tuple[Any, ...] = ()  # extra spell icons / figure objs / Card objs
    replay_key: Any = None  # stable animation/replay identity for spell beats


@dataclass(frozen=True)
class ConquerEvent:
    """Legacy event record retained for backward-compatible imports.

    The new conquer panel derives state from the game directly, but tests and
    external callers may still import this name.
    """
    key: str
    phase: str
    title: str
    detail: str = ''
    tone: str = 'info'
    spell_names: Tuple[str, ...] = field(default_factory=tuple)
    order: int = 0
    spell_side: str = ''
    spell_role: str = ''


def event_spells_by_side(events: Iterable[ConquerEvent]) -> dict:
    """Deprecated: kept for legacy imports; the new timeline panel does not use this."""
    return {'own': [], 'opponent': [], 'own_roles': {}, 'opponent_roles': {}}


def infer_spell_metadata(data: dict) -> Tuple[str, str]:
    """Deprecated: returns ('', '').  Retained for backward-compatible imports."""
    return (data.get('spell_side', '') or ''), (data.get('spell_role', '') or '')


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


def _civil_war_pick_flow_active(game: Any) -> bool:
    if _has_modifier(game, 'Royal Decree'):
        return False
    return bool(
        _has_modifier(game, 'Civil War')
        or _get(game, 'civil_war_awaiting_second', False)
        or _get(game, 'civil_war_defender_second', False)
    )


def _battle_modifiers(game: Any) -> List[dict]:
    modifiers = _get(game, 'battle_modifier', [])
    if not isinstance(modifiers, list):
        return []
    return [mod for mod in modifiers if isinstance(mod, dict)]


def _figure_name(figure: Any, fallback: str) -> str:
    return _get(figure, 'name', fallback) or fallback


def _figure_is_revealed(field_screen: Any, figure: Any) -> bool:
    """Return True when the local player is allowed to know ``figure``'s name.

    Mirrors the field-screen icon-cache visibility rule so the info panel
    never leaks an opponent's identity before the actual reveal moment.
    """
    if figure is None:
        return False
    if field_screen is None:
        return True
    cache = getattr(field_screen, 'icon_cache', None) or {}
    cached = cache.get(_get(figure, 'id'))
    if cached is None:
        return True
    return bool(getattr(cached, 'is_visible', True))


def _figure_label(figure: Any, field_screen: Any, *, own: bool,
                  fallback: str = 'this figure') -> str:
    """Return a name-or-placeholder label safe for the info panel.

    Own figures always reveal the name.  Opponent figures only reveal it
    when the field treats them as visible (Maharaja, All Seeing Eye, etc.)
    AND the battle has started — until then we use ``"the chosen figure"``
    so the info panel cannot leak identity.
    """
    if own:
        return _figure_name(figure, fallback)
    if _figure_is_revealed(field_screen, figure):
        return _figure_name(figure, fallback)
    return 'the chosen figure'


def _pending_confirmation_objective(field_screen: Any) -> Optional[ConquerObjective]:
    if not field_screen:
        return None

    advance = _get(field_screen, '_pending_advance_figure')
    if advance:
        name = _figure_label(advance, field_screen, own=True)
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
        name = _figure_label(defender, field_screen, own=False)
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
        name = _figure_label(own_defender, field_screen, own=True)
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

    advancing_id = _get(game, 'advancing_figure_id')
    defending_id = _get(game, 'defending_figure_id')
    player_id = _get(game, 'player_id')
    advancing_player_id = _get(game, 'advancing_player_id')

    if (_get(game, 'pending_forced_advance', False)
            and not advancing_id):
        return ConquerObjective(
            phase='advance',
            headline='Choose your battle figure',
            instruction='Select one of your legal figures on the field to advance.',
            target_tab='field',
            primary_action='select_advance',
            tone='action',
        )

    if (_civil_war_pick_flow_active(game)
            and _get(game, 'civil_war_awaiting_second', False)
            and advancing_id):
        return ConquerObjective(
            phase='advance',
            headline='Civil War: optional second attacker',
            instruction='Select a second same-color village figure, or skip the second figure.',
            target_tab='field',
            primary_action='select_second',
            tone='action',
        )

    if (_civil_war_pick_flow_active(game)
            and _get(game, 'civil_war_defender_second', False)
            and advancing_id):
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
            and advancing_id
            and _get(game, 'turn', False)):
        restriction = ''
        if _has_modifier(game, 'Royal Decree'):
            restriction = ' Royal Decree: castle figures only.'
        elif _has_modifier(game, 'Peasant War'):
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

    if _get(game, 'pending_conquer_own_defender_selection', False) and advancing_id:
        return ConquerObjective(
            phase='defender',
            headline='Invader Swap: choose your defender',
            instruction='Select one of your own legal figures to defend against the invader.',
            target_tab='field',
            primary_action='select_own_defender',
            tone='action',
        )

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
        # Tactics-hand games never sit in moves_phase server-side, but a
        # stale client snapshot may briefly report it.  Steer the objective
        # to the unified battle view rather than the (gone) battle shop.
        if _get(game, 'conquer_move_model', 'battle_move') == 'tactics_hand':
            return ConquerObjective(
                phase='moves',
                headline='Pick your tactic',
                instruction='Select a card from your tactics hand to play.',
                target_tab='field',
                primary_action='play_tactic',
                tone='action',
            )
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
            headline='Moves locked in',
            instruction='Your battle moves are committed. Opponent is choosing theirs.',
            target_tab='field',
            waiting=True,
            tone='waiting',
        )

    if (_get(game, 'both_battle_moves_ready', False)
            or (_get(game, 'battle_confirmed', False)
                and _get(game, 'battle_turn_player_id') is not None)):
        your_turn = _get(game, 'battle_turn_player_id') == player_id
        tactics_hand = _get(game, 'conquer_move_model', 'battle_move') == 'tactics_hand'
        if tactics_hand:
            headline = 'Play a battle tactic' if your_turn else 'Opponent battle tactic'
            instruction = ('Choose a tactic and confirm it.' if your_turn else
                           'Waiting for the opponent to play.')
            target_tab = 'field'
            primary_action = 'play_tactic' if your_turn else None
        else:
            headline = 'Play a battle move' if your_turn else 'Opponent battle move'
            instruction = ('Choose a move and confirm it.' if your_turn else
                           'Waiting for the opponent to play.')
            target_tab = 'battle'
            primary_action = 'play_move' if your_turn else None
        return ConquerObjective(
            phase='battle',
            headline=headline,
            instruction=instruction,
            target_tab=target_tab,
            primary_action=primary_action,
            waiting=not your_turn,
            tone='action' if your_turn else 'waiting',
        )

    if _get(game, 'pending_battle_ready', False):
        # Both figures are set but the battle has not been confirmed yet.
        # Keep the player on the field so they can clearly see the matchup
        # before the move-selection phase opens — flipping straight to the
        # battle shop here looks like a premature jump.
        return ConquerObjective(
            phase='moves',
            headline='Both fighters chosen',
            instruction='Conquer battles fight automatically — preparing the move-selection phase.',
            target_tab='field',
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
        instruction='The defender is taking their turn. The flow will resume automatically.',
        target_tab='field',
        waiting=True,
        tone='waiting',
    )


def spell_names_from_events(events: Iterable[ConquerEvent]) -> Tuple[str, ...]:
    """Deprecated: legacy helper retained for backward-compatible imports."""
    seen = set()
    names = []
    for event in events:
        for name in getattr(event, 'spell_names', ()):
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return tuple(names)


# ---------------------------------------------------------- timeline derivation


def _opponent_name(game: Any) -> str:
    return _get(game, 'opponent_name', '') or 'Defender'


def _own_prelude_spells(game: Any) -> List[dict]:
    """Return prelude spells cast by us this game (snapshot from game_start)."""
    if game is None:
        return []
    snap = _get(game, 'conquer_own_prelude_spells', None)
    if snap:
        return [s for s in snap if isinstance(s, dict)]
    # Fallback: scan cached_active_spells for legacy phase_cast/prelude markers.
    player_id = _get(game, 'player_id')
    spells = _get(game, 'cached_active_spells', []) or []
    out = []
    for s in spells:
        if not isinstance(s, dict):
            continue
        if s.get('player_id') != player_id:
            continue
        if s.get('phase_cast') == 'prelude' or s.get('spell_type') == 'prelude':
            out.append(s)
    return out


def _opp_prelude_spells(game: Any) -> List[dict]:
    if game is None:
        return []
    snap = _get(game, 'conquer_opp_prelude_spells', None)
    if snap:
        return [s for s in snap if isinstance(s, dict)]
    player_id = _get(game, 'player_id')
    spells = _get(game, 'cached_active_spells', []) or []
    out = []
    for s in spells:
        if not isinstance(s, dict):
            continue
        if s.get('player_id') == player_id:
            continue
        if s.get('phase_cast') == 'prelude' or s.get('spell_type') == 'prelude':
            out.append(s)
    return out


def _counter_spells(game: Any) -> List[dict]:
    """Return any counter spells cast against the current advance, if any."""
    if game is None:
        return []
    modifiers = _battle_modifiers(game)
    spells = _get(game, 'cached_active_spells', []) or []
    out = []
    seen = set()

    # Battle-modifier spells (e.g., Blitzkrieg) can be cast either as a
    # prelude or as a counter.  When cast in prelude they still register
    # a battle modifier, which would otherwise also surface them in the
    # counter slot — producing a duplicate alongside the prelude slot.
    # Collect (player_id, spell_name) pairs from the prelude snapshots so
    # we can suppress that duplicate while still showing genuine
    # counter-cast spells.
    own_player_id = _get(game, 'player_id')
    prelude_keys: set = set()
    for snap in _own_prelude_spells(game) or []:
        if isinstance(snap, dict) and snap.get('spell_name'):
            prelude_keys.add((own_player_id, snap.get('spell_name')))
    for snap in _opp_prelude_spells(game) or []:
        if isinstance(snap, dict) and snap.get('spell_name'):
            prelude_keys.add(('opp', snap.get('spell_name')))

    def _prelude_player_key(player_id: Any) -> Any:
        if own_player_id is not None and player_id is not None and player_id == own_player_id:
            return own_player_id
        return 'opp'

    def is_prelude_cast(spell: dict) -> bool:
        spell_name = spell.get('spell_name')
        if not spell_name:
            return False
        effect_data = _spell_effect_data(spell)
        if effect_data.get('prelude_origin') or effect_data.get('prelude_status'):
            return True
        key = (_prelude_player_key(spell.get('player_id')), spell_name)
        return key in prelude_keys

    def marker(spell: dict) -> Tuple[Any, Any, Any]:
        return (spell.get('id'), spell.get('player_id'), spell.get('spell_name'))

    def add(spell: dict) -> None:
        key = marker(spell)
        if key in seen:
            return
        seen.add(key)
        out.append(spell)

    def matching_counter_modifier(spell: dict) -> Optional[dict]:
        spell_name = spell.get('spell_name')
        if spell_name not in _COUNTER_TIMELINE_MODIFIER_SPELLS:
            return None
        spell_id = spell.get('id')
        player_id = spell.get('player_id')
        for modifier in modifiers:
            if modifier.get('type') != spell_name:
                continue
            modifier_spell_id = modifier.get('spell_id')
            if modifier_spell_id is not None and spell_id is not None:
                if str(modifier_spell_id) == str(spell_id):
                    return modifier
                continue
            caster_id = modifier.get('caster_id')
            if caster_id is None or player_id is None or str(caster_id) == str(player_id):
                return modifier
        return None

    for spell in spells:
        if not isinstance(spell, dict):
            continue
        effect_data = _spell_effect_data(spell)
        if is_prelude_cast(spell):
            continue
        counter_modifier = matching_counter_modifier(spell)
        if (effect_data.get('counter_origin')
                or effect_data.get('battle_modifier_added') in _COUNTER_TIMELINE_MODIFIER_SPELLS
                or counter_modifier is not None
                or spell.get('phase_cast') == 'counter'
                or spell.get('spell_role') == 'counter'
                or spell.get('type') == 'counter_spell'
                or spell.get('spell_type') == 'counter'):
            if not _counter_spell_matches_current_context(game, spell):
                continue
            add(spell)

    for modifier in modifiers:
        modifier_type = modifier.get('type')
        if modifier_type not in _COUNTER_TIMELINE_MODIFIER_SPELLS:
            continue
        spell_id = modifier.get('spell_id')
        caster_id = (
            modifier.get('caster_id')
            or _get(game, 'invader_player_id')
            or _get(game, 'advancing_player_id')
        )
        # If a matching prelude snapshot exists for this modifier, the
        # modifier was added by the prelude spell — already represented in
        # the prelude slot, so don't re-surface it as a counter step.
        if (_prelude_player_key(caster_id), modifier_type) in prelude_keys:
            continue
        already_present = any(
            spell.get('spell_name') == modifier_type
            and (spell_id is None or spell.get('id') is None or str(spell.get('id')) == str(spell_id))
            and (caster_id is None or spell.get('player_id') is None or str(spell.get('player_id')) == str(caster_id))
            for spell in out
        )
        if already_present:
            continue
        add({
            'id': spell_id,
            'player_id': caster_id,
            'spell_name': modifier_type,
            'effect_data': {
                'battle_modifier_origin': True,
                'battle_modifier_added': modifier_type,
                'caster_name': modifier.get('caster_name'),
            },
        })
    return out


def _spell_effect_data(spell_info: dict) -> dict:
    data = spell_info.get('effect_data') if isinstance(spell_info, dict) else {}
    return data if isinstance(data, dict) else {}


def _card_assets(cards: Any, *, reveal: bool = True) -> Tuple[dict, ...]:
    if not isinstance(cards, list):
        return ()
    return tuple(
        {'kind': 'card', 'card': card, 'reveal': reveal}
        for card in cards
        if isinstance(card, dict)
    )


def _forced_deal_user_cards(effect_data: dict, *, own: bool) -> Tuple[List[dict], List[dict]]:
    """Return (lost, gained) cards from the local user's perspective."""
    if own:
        lost = effect_data.get('cards_given') or effect_data.get('caster_gave') or []
        gained = effect_data.get('cards_received') or effect_data.get('caster_received') or []
    else:
        lost = effect_data.get('opponent_gave') or effect_data.get('cards_given') or []
        gained = effect_data.get('opponent_received') or effect_data.get('cards_received') or []
    lost = lost if isinstance(lost, list) else []
    gained = gained if isinstance(gained, list) else []
    return lost, gained


def _forced_deal_card_assets(spell_info: dict, *, own: bool) -> Tuple[dict, ...]:
    lost, gained = _forced_deal_user_cards(_spell_effect_data(spell_info), own=own)
    assets: List[dict] = []
    for card in lost:
        if isinstance(card, dict):
            assets.append({
                'kind': 'card', 'card': card, 'reveal': True,
                'role': 'lost', 'label': 'Lost', 'tone': 'bad',
                'dim': True, 'crossed': True,
            })
    for card in gained:
        if isinstance(card, dict):
            assets.append({
                'kind': 'card', 'card': card, 'reveal': True,
                'role': 'gained', 'label': 'Gained', 'tone': 'good',
            })
    return tuple(assets)


def _dump_cards_card_assets(spell_info: dict, *, own: bool) -> Tuple[dict, ...]:
    """Cards lost (old hand) and gained (new hand) from the user's POV.

    Mirrors Forced Deal so the timeline info box shows what each player
    discarded vs. redrew. When ``own`` is False, the user is the
    non-caster: lost cards are revealed (the user is allowed to know what
    they discarded) and the opponent's new hand stays hidden.
    """
    effect_data = _spell_effect_data(spell_info)
    if own:
        lost = effect_data.get('caster_dumped_cards') or []
        gained = effect_data.get('drawn_cards') or []
        gained_reveal = True
    else:
        lost = effect_data.get('opponent_dumped_cards') or []
        gained = effect_data.get('opponent_drawn_cards') or []
        gained_reveal = False
    assets: List[dict] = []
    for card in lost if isinstance(lost, list) else []:
        if isinstance(card, dict):
            assets.append({
                'kind': 'card', 'card': card, 'reveal': True,
                'role': 'lost', 'label': 'Lost', 'tone': 'bad',
                'dim': True, 'crossed': True,
            })
    for card in gained if isinstance(gained, list) else []:
        if isinstance(card, dict):
            assets.append({
                'kind': 'card', 'card': card, 'reveal': gained_reveal,
                'role': 'gained', 'label': 'Gained' if gained_reveal else '',
                'tone': 'good',
            })
    return tuple(assets)


def _resource_asset(label: str, value: Any = '', tone: str = 'neutral') -> dict:
    return {'kind': 'resource', 'label': label, 'value': value, 'tone': tone}


def _prelude_effect_line(spell_info: dict, *, own: bool) -> str:
    spell_name = spell_info.get('spell_name') or 'Prelude spell'
    effect_data = _spell_effect_data(spell_info)
    target_name = (
        spell_info.get('target_figure_name')
        or effect_data.get('target_figure_name')
        or effect_data.get('destroyed_figure_name')
    )

    if spell_name == 'Fill up to 10':
        previous_total = effect_data.get('previous_total')
        new_total = effect_data.get('new_total')
        current_total = effect_data.get('current_total')
        drawn = effect_data.get('drawn_cards') or []
        drawn_count = effect_data.get('cards_drawn', len(drawn))
        if previous_total is not None and new_total is not None:
            return (f'Fill up to 10: main hand {previous_total} -> '
                    f'{new_total}; drew {drawn_count} card(s).')
        if current_total is not None:
            return f'Fill up to 10: main hand already at {current_total}; no cards drawn.'
        return f'Fill up to 10: drew {drawn_count} main card(s).'

    if spell_name in ('Draw 2 MainCards', 'Draw 2 SideCards'):
        drawn = effect_data.get('drawn_cards') or []
        drawn_count = effect_data.get('cards_drawn', len(drawn) or 2)
        card_type = effect_data.get('card_type') or ('side' if 'Side' in spell_name else 'main')
        return f'{spell_name}: drew {drawn_count} {card_type} card(s).'

    if spell_name == 'Poison':
        return (f'Poison: {target_name} receives -6 battle power.'
                if target_name else 'Poison: target receives -6 battle power.')

    if spell_name == 'Health Boost':
        return (f'Health Boost: {target_name} receives +6 battle power.'
                if target_name else 'Health Boost: target receives +6 battle power.')

    if spell_name == 'Explosion':
        card_count = effect_data.get('card_count')
        destroyed = target_name or 'a figure'
        if card_count is not None:
            return f'Explosion: destroyed {destroyed}; {card_count} card(s) returned to the deck.'
        return f'Explosion: destroyed {destroyed}.'

    if spell_name == 'Dump Cards':
        own_dumped = effect_data.get('caster_dumped') if own else effect_data.get('opponent_dumped')
        opp_dumped = effect_data.get('opponent_dumped') if own else effect_data.get('caster_dumped')
        return (f'Dump Cards: you discarded {own_dumped or 0} card(s); '
                f'opponent discarded {opp_dumped or 0}; both redrew.')

    if spell_name == 'Forced Deal':
        lost, gained = _forced_deal_user_cards(effect_data, own=own)
        if lost or gained:
            return f'Forced Deal: you lost {len(lost)} card(s) and gained {len(gained)}.'
        return 'Forced Deal: exchanged 2 random main cards.'

    if spell_name == 'Invader Swap':
        return 'Invader Swap: the battle roles changed before the first advance.'

    if spell_name == 'Blitzkrieg':
        return 'Blitzkrieg: defender counter-advance is blocked; the attacker chooses the defender.'

    if spell_name in ('Peasant War', 'Civil War'):
        return f'{spell_name}: battle rule modifier applied.'

    if spell_info.get('spell_name'):
        return f'{spell_name}: effect resolved.'
    return 'Prelude spell resolved.'


def _unique_card_assets(cards: Iterable[Any], *, reveal: bool) -> Tuple[dict, ...]:
    seen = set()
    assets: List[dict] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        key = card.get('id') if card.get('id') is not None else repr(sorted(card.items()))
        if key in seen:
            continue
        seen.add(key)
        assets.append({'kind': 'card', 'card': card, 'reveal': reveal})
    return tuple(assets)


def _prelude_target_id(spell: dict, effect_data: dict) -> Any:
    return (
        spell.get('target_figure_id')
        or effect_data.get('target_figure_id')
        or effect_data.get('destroyed_figure_id')
    )


def _stable_spell_token(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _counter_context_tuple(context: Any) -> Tuple[Any, Any, Any, Any]:
    if not isinstance(context, dict):
        return (None, None, None, None)
    return (
        _stable_spell_token(context.get('round')),
        _stable_spell_token(context.get('advancing_player_id')),
        _stable_spell_token(context.get('advancing_figure_id')),
        _stable_spell_token(context.get('advancing_figure_id_2')),
    )


def _spell_replay_key(step_kind: str, spell: dict) -> Any:
    """Return a stable identity for a prelude/counter spell timeline beat."""
    if not isinstance(spell, dict):
        return None
    spell_id = spell.get('id') or spell.get('spell_id')
    if spell_id is not None:
        return ('spell', step_kind, _stable_spell_token(spell_id))
    effect_data = _spell_effect_data(spell)
    return (
        'spell',
        step_kind,
        _stable_spell_token(spell.get('spell_name')),
        _stable_spell_token(spell.get('player_id')),
        _stable_spell_token(_prelude_target_id(spell, effect_data)),
        _counter_context_tuple(effect_data.get('conquer_counter_context')),
    )


def _same_identity(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    return str(left) == str(right)


def _entry_get(entry: Any, name: str, default: Any = None) -> Any:
    if isinstance(entry, dict):
        return entry.get(name, default)
    return getattr(entry, name, default)


def _defender_selected_by_player(game: Any, field_screen: Any,
                                  defender_id: Any, player_id: Any) -> bool:
    """True when the local player explicitly selected this opponent defender."""
    if defender_id is None or player_id is None:
        return False

    local_pick = _get(field_screen, '_player_selected_defender_id')
    if _same_identity(local_pick, defender_id):
        return True

    logs = _get(game, 'log_entries', []) or []
    current_round = _get(game, 'current_round', None)
    for entry in reversed(list(logs)):
        if _entry_get(entry, 'type') != 'select_defender':
            continue
        if not _same_identity(_entry_get(entry, 'player_id'), player_id):
            continue
        entry_round = _entry_get(entry, 'round_number', None)
        if (current_round is not None and entry_round is not None
                and not _same_identity(entry_round, current_round)):
            continue
        return True
    return False


def _counter_spell_matches_current_context(game: Any, spell: dict) -> bool:
    """Prefer counter records that belong to the current advance.

    Newer counter spell rows carry ``conquer_counter_context``.  Older saves
    do not, so they keep the legacy same-round/target fallback instead of
    disappearing from historical battle timelines.
    """
    if game is None or not isinstance(spell, dict):
        return False
    effect_data = _spell_effect_data(spell)
    context = effect_data.get('conquer_counter_context')
    if isinstance(context, dict):
        checks = (
            ('round', _get(game, 'current_round', None)),
            ('advancing_player_id', _get(game, 'advancing_player_id', None)),
            ('advancing_figure_id', _get(game, 'advancing_figure_id', None)),
            ('advancing_figure_id_2', _get(game, 'advancing_figure_id_2', None)),
        )
        for key, current in checks:
            if current is None:
                continue
            if key in context and not _same_identity(context.get(key), current):
                return False
        return True

    cast_round = spell.get('cast_round')
    current_round = _get(game, 'current_round', None)
    if cast_round is not None and current_round is not None:
        if not _same_identity(cast_round, current_round):
            return False

    if spell.get('spell_name') == 'Poison':
        target_id = _prelude_target_id(spell, effect_data)
        advancing_ids = {
            _stable_spell_token(_get(game, 'advancing_figure_id', None)),
            _stable_spell_token(_get(game, 'advancing_figure_id_2', None)),
        }
        advancing_ids.discard(None)
        if target_id is not None and advancing_ids:
            if _stable_spell_token(target_id) not in advancing_ids:
                return False
    return True


def _prelude_target_asset(spell: dict, effect_data: dict, *,
                          field_screen: Any = None,
                          game: Any = None) -> Tuple[dict, ...]:
    target = spell.get('target_figure') if isinstance(spell, dict) else None
    if target is None:
        target = _figure_by_id(field_screen, _prelude_target_id(spell, effect_data))
    if target is None:
        return ()

    own_target = _get(target, 'player_id') == _get(game, 'player_id')
    reveal = bool(own_target)
    if not reveal and field_screen is not None:
        cached = (getattr(field_screen, 'icon_cache', None) or {}).get(_get(target, 'id'))
        reveal = bool(cached and getattr(cached, 'is_visible', False))
    return _figure_asset(
        target,
        side='own' if own_target else 'opponent',
        reveal=reveal,
    )


def _prelude_info_assets(spells: List[dict], *, own: bool,
                         field_screen: Any = None,
                         game: Any = None) -> Tuple[dict, ...]:
    assets: List[dict] = []
    for spell in spells:
        if not isinstance(spell, dict):
            continue
        spell_name = spell.get('spell_name')
        if spell_name:
            assets.append({'kind': 'spell', 'name': spell_name})

        effect_data = _spell_effect_data(spell)
        drawn_cards = effect_data.get('drawn_cards') or []

        assets.extend(_prelude_target_asset(
            spell, effect_data, field_screen=field_screen, game=game))

        if spell_name == 'Forced Deal':
            assets.extend(_forced_deal_card_assets(spell, own=own))
            continue

        if spell_name == 'Dump Cards':
            assets.extend(_dump_cards_card_assets(spell, own=own))
            continue

        if own:
            assets.extend(_card_assets(drawn_cards, reveal=True))
        else:
            hidden_cards: List[Any] = []
            for source in (
                    drawn_cards,
                    effect_data.get('opponent_drawn_cards') or [],
                    effect_data.get('opponent_received') or [],
                    effect_data.get('cards_received') or []):
                if isinstance(source, list):
                    hidden_cards.extend(source)
            assets.extend(_unique_card_assets(hidden_cards, reveal=False))

        if spell_name == 'Fill up to 10':
            previous_total = effect_data.get('previous_total')
            new_total = effect_data.get('new_total')
            current_total = effect_data.get('current_total')
            drawn_count = effect_data.get('cards_drawn')
            if previous_total is not None and new_total is not None:
                assets.append(_resource_asset('Main hand', f'{previous_total} -> {new_total}', 'good'))
            elif current_total is not None:
                assets.append(_resource_asset('Main hand', f'{current_total}', 'neutral'))
            if drawn_count is not None:
                assets.append(_resource_asset('Drawn', drawn_count, 'good' if drawn_count else 'neutral'))
        elif spell_name == 'Health Boost':
            assets.append(_resource_asset('Battle power', '+6', 'good'))
        elif spell_name == 'Poison':
            assets.append(_resource_asset('Battle power', '-6', 'bad'))
        elif spell_name == 'Explosion':
            card_count = effect_data.get('card_count')
            if card_count is not None:
                assets.append(_resource_asset('Cards returned', card_count, 'warning'))

    return tuple(assets)


def _prelude_body(spells: List[dict], *, own: bool, empty: str) -> str:
    if not spells:
        return empty
    return ' '.join(_prelude_effect_line(spell, own=own) for spell in spells)


def _figure_asset(figure: Any, *, side: str, reveal: bool) -> Tuple[dict, ...]:
    if figure is None:
        return ()
    return ({'kind': 'figure', 'figure': figure, 'side': side, 'reveal': reveal},)


def _figure_assets(entries: Iterable[Tuple[Any, str, bool]]) -> Tuple[dict, ...]:
    assets: List[dict] = []
    seen = set()
    for figure, side, reveal in entries:
        if figure is None:
            continue
        figure_id = _get(figure, 'id')
        key = figure_id if figure_id is not None else id(figure)
        if key in seen:
            continue
        seen.add(key)
        assets.append({
            'kind': 'figure',
            'figure': figure,
            'side': side,
            'reveal': bool(reveal),
        })
    return tuple(assets)


def _figure_by_id(field_screen: Any, fig_id: Any) -> Any:
    if not fig_id or field_screen is None:
        return None
    for fig in _get(field_screen, 'figures', []) or []:
        if _get(fig, 'id') == fig_id:
            return fig
    return None


def _format_number(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f'{number:.1f}'


def _effective_land_bonus(game: Any) -> Tuple[Any, Any]:
    """(suit, value) of the land bonus with Landslide inversion applied."""
    getter = getattr(game, 'effective_land_bonus', None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            pass
    return _get(game, 'land_suit_bonus_suit'), _get(game, 'land_suit_bonus_value')


def _land_info_assets(game: Any, opponent_name: str) -> Tuple[dict, ...]:
    assets: List[dict] = []
    gold_rate = _format_number(_get(game, 'land_gold_rate'))
    suit, raw_bonus = _effective_land_bonus(game)
    bonus = _format_number(raw_bonus)

    if gold_rate is not None:
        assets.append(_resource_asset('Gold/hr', gold_rate, 'good'))
    if suit:
        inverted = isinstance(raw_bonus, (int, float)) and raw_bonus < 0
        bonus_text = (f'+{bonus}' if bonus and not inverted else (bonus or ''))
        assets.append(_resource_asset(
            'Suit bonus', f'{bonus_text} {suit}'.strip(),
            'bad' if inverted else 'good'))
    assets.append(_resource_asset('Defender', opponent_name, 'warning'))
    return tuple(assets)


def _land_overview_text(game: Any) -> Tuple[str, str]:
    tier = _get(game, 'land_tier')
    suit, bonus = _effective_land_bonus(game)
    gold_rate = _format_number(_get(game, 'land_gold_rate'))
    opponent = _opponent_name(game)
    title = f'Tier {tier} Land' if tier else 'Conquer Battle'
    parts = [f'You are fighting {opponent} for {title.lower()}.']
    if gold_rate is not None:
        parts.append(f'It produces {gold_rate} gold/hour.')
    if suit:
        if isinstance(bonus, (int, float)) and bonus < 0:
            parts.append(f'Suit bonus: {suit} ({bonus}, inverted by Landslide).')
        else:
            b = f' (+{_format_number(bonus)})' if bonus else ''
            parts.append(f'Suit bonus: {suit}{b}.')
    return title, ' '.join(parts)


def derive_conquer_timeline(game: Any, state: Any = None,
                            field_screen: Any = None,
                            shop_screen: Any = None) -> List[TimelineStep]:
    """Build the ordered list of timeline steps from current game state.

    Pure read-only.  Each step is either ``completed``, ``active``, or
    pending.  Exactly one step is marked ``active`` (or none, when the
    timeline has finished i.e. battle in progress / finished).
    """
    if game is None:
        return [TimelineStep(kind='overview', title='Loading…')]

    opp_name = _opponent_name(game)
    player_id = _get(game, 'player_id')
    advancing_player_id = _get(game, 'advancing_player_id')
    advancing_id = _get(game, 'advancing_figure_id')
    advancing_id_2 = _get(game, 'advancing_figure_id_2')
    defending_id = _get(game, 'defending_figure_id')
    defending_id_2 = _get(game, 'defending_figure_id_2')
    own_is_attacker = (advancing_player_id == player_id) if advancing_player_id else None
    battle_confirmed = bool(_get(game, 'battle_confirmed', False))
    battle_started = battle_confirmed and _get(game, 'battle_turn_player_id') is not None
    pending_prelude = _pending_prelude_target(game, state)
    own_preludes = _own_prelude_spells(game)
    opp_preludes = _opp_prelude_spells(game)
    counter_spells = _counter_spells(game)

    steps: List[TimelineStep] = []

    # 0) Overview --------------------------------------------------------
    title, body = _land_overview_text(game)
    steps.append(TimelineStep(
        kind='overview',
        title=title,
        owner='',
        icon_kind='land',
        icon_payload={
            'tier': _get(game, 'land_tier'),
            'suit': _effective_land_bonus(game)[0],
            'bonus': _effective_land_bonus(game)[1],
        },
        completed=True,
        info_headline=title,
        info_body=body,
        info_assets=_land_info_assets(game, opp_name),
    ))

    # 1) Own prelude -----------------------------------------------------
    own_pre_active = bool(pending_prelude)
    own_pre_done = not own_pre_active
    pending_prelude_name = (
        pending_prelude.get('spell_name')
        if isinstance(pending_prelude, dict) else None
    )
    own_pre_step = TimelineStep(
        kind='prelude_own',
        title='Your Prelude',
        owner='you',
        icon_kind='spell' if (own_preludes or pending_prelude_name) else 'none',
        icon_payload=(
            own_preludes[0].get('spell_name') if own_preludes
            else pending_prelude_name
        ),
        sub_icons=tuple(s.get('spell_name') for s in own_preludes[1:]),
        completed=own_pre_done,
        active=own_pre_active,
        interactive=own_pre_active,
        primary_action='select_target' if own_pre_active else None,
        tone='action' if own_pre_active else 'good' if own_pre_done else 'neutral',
        sidenote='No prelude' if not own_preludes and not own_pre_active else '',
        info_headline=(
            f'Resolve {pending_prelude.get("spell_name", "prelude spell")}'
            if isinstance(pending_prelude, dict) else
            (f'You cast {", ".join(s.get("spell_name", "") for s in own_preludes)}'
             if own_preludes else 'Your prelude')
        ),
        info_body=(
            ('Select ' +
             ('one of your figures' if isinstance(pending_prelude, dict)
              and pending_prelude.get('target_scope') == 'own'
              else "one of the defender's figures") + ' on the field.')
            if own_pre_active
            else _prelude_body(
                own_preludes,
                own=True,
                empty='No prelude spell was configured.',
            )
        ),
        info_assets=_prelude_info_assets(
            own_preludes, own=True, field_screen=field_screen, game=game),
        replay_key=(
            _spell_replay_key('prelude_own', own_preludes[0])
            if own_preludes else None
        ),
    )
    steps.append(own_pre_step)

    # 2) Opponent prelude ------------------------------------------------
    opp_pre_done = not own_pre_active
    opp_pre_step = TimelineStep(
        kind='prelude_opp',
        title=f"{opp_name}'s Prelude",
        owner=opp_name,
        icon_kind='spell' if opp_preludes else 'none',
        icon_payload=(opp_preludes[0].get('spell_name') if opp_preludes else None),
        sub_icons=tuple(s.get('spell_name') for s in opp_preludes[1:]),
        completed=opp_pre_done,
        tone='warning' if opp_preludes else 'neutral',
        sidenote='No prelude' if not opp_preludes and not own_pre_active else '',
        info_headline=(f'{opp_name} cast ' +
                       ', '.join(s.get('spell_name', '') for s in opp_preludes)
                       if opp_preludes else f"{opp_name}'s prelude"),
        info_body=_prelude_body(
            opp_preludes,
            own=False,
            empty='No prelude effects from the opponent.',
        ),
        info_assets=_prelude_info_assets(
            opp_preludes, own=False, field_screen=field_screen, game=game),
        replay_key=(
            _spell_replay_key('prelude_opp', opp_preludes[0])
            if opp_preludes else None
        ),
    )
    steps.append(opp_pre_step)

    # Helper flags for downstream visibility
    prelude_phase_passed = not own_pre_active

    # 3) Attacker --------------------------------------------------------
    attacker_pending_advance_local = (
        bool(_get(field_screen, '_pending_advance_figure'))
        if field_screen is not None else False
    )
    pending_defender_select_turn = bool(
        advancing_id
        and _get(game, 'pending_defender_selection', False)
        and _get(game, 'turn', False)
    )
    pending_own_defender_select = bool(
        advancing_id
        and _get(game, 'pending_conquer_own_defender_selection', False)
    )
    attacker_second_active = bool(
        advancing_id
        and _civil_war_pick_flow_active(game)
        and _get(game, 'civil_war_awaiting_second', False)
    )
    attacker_select_active = bool(
        _get(game, 'pending_forced_advance', False) and not advancing_id
    ) or bool(
        _get(game, 'turn', False)
        and not advancing_id
        and not pending_defender_select_turn
        and not pending_own_defender_select
        and not _get(game, 'battle_moves_phase', False)
    ) or attacker_second_active or attacker_pending_advance_local
    attacker_done = bool(advancing_id) and not attacker_second_active
    attacker_owner = ''
    if advancing_player_id:
        attacker_owner = 'you' if own_is_attacker else opp_name
    elif _get(game, 'turn', False):
        attacker_owner = 'you'
    else:
        attacker_owner = opp_name
    attacker_figure = _figure_by_id(field_screen, advancing_id) if advancing_id else None
    attacker_figure_2 = _figure_by_id(field_screen, advancing_id_2) if advancing_id_2 else None
    attacker_pending_figure = _get(field_screen, '_pending_advance_figure')
    attacker_asset_figure = attacker_pending_figure or attacker_figure
    attacker_side = 'own' if own_is_attacker or attacker_pending_figure else 'opponent'
    attacker_reveal = bool(attacker_side == 'own' or battle_started or
                           _figure_is_revealed(field_screen, attacker_asset_figure))
    attacker_second_reveal = bool(attacker_side == 'own' or battle_started or
                                  _figure_is_revealed(field_screen, attacker_figure_2))
    attacker_info_assets = _figure_assets((
        (attacker_figure, 'own' if own_is_attacker else 'opponent',
         bool(own_is_attacker or battle_started or _figure_is_revealed(field_screen, attacker_figure))),
        (attacker_figure_2, 'own' if own_is_attacker else 'opponent', attacker_second_reveal),
        (attacker_pending_figure, attacker_side, attacker_reveal),
    ))
    attacker_step = TimelineStep(
        kind='attacker',
        title='Attacking Figure',
        owner=attacker_owner,
        icon_kind='figure' if attacker_figure else 'none',
        icon_payload={
            'figure': attacker_figure,
            'side': 'own' if own_is_attacker else 'opponent',
            'reveal': bool(own_is_attacker or battle_started or
                           _figure_is_revealed(field_screen, attacker_figure)),
        } if attacker_figure else None,
        completed=attacker_done and not attacker_pending_advance_local,
        active=(attacker_select_active or attacker_pending_advance_local) and prelude_phase_passed,
        interactive=attacker_select_active or attacker_pending_advance_local,
        primary_action=(
            'confirm' if attacker_pending_advance_local
            else 'select_second' if attacker_second_active
            else 'select_advance' if attacker_select_active
            else None
        ),
        tone=(
            'action' if (attacker_select_active or attacker_pending_advance_local)
            else 'good' if attacker_done else 'neutral'
        ),
        sidenote='Civil War' if attacker_second_active or advancing_id_2 else '',
        info_headline=(
            'Confirm your second attacker' if attacker_pending_advance_local and attacker_second_active
            else 'Confirm your attacker' if attacker_pending_advance_local
            else 'Choose your second Civil War attacker' if attacker_second_active
            else 'Choose your attacker' if attacker_select_active and own_is_attacker is not False
            else 'Opponent attacker' if attacker_done and not own_is_attacker
            else 'Your attacker' if attacker_done and own_is_attacker
            else 'Waiting for attacker'
        ),
        info_body=(
            'Press Confirm to commit, or Cancel to pick another figure.'
            if attacker_pending_advance_local
            else 'Select another village figure of the same color, or skip the second Civil War figure.'
            if attacker_second_active
            else 'Select one of your legal figures on the field to advance.'
            if attacker_select_active
            else (f'{_figure_label(attacker_figure, field_screen, own=bool(own_is_attacker), fallback="Attacker")} '
                  'is locked in as the attacker.'
                  if attacker_done else '')
        ),
        info_assets=attacker_info_assets,
    )
    steps.append(attacker_step)

    # 4) Counter spell (optional) ----------------------------------------
    if counter_spells:
        first = counter_spells[0]
        counter_own = first.get('player_id') == player_id
        counter_owner = 'you' if counter_own else opp_name
        counter_names = ', '.join(
            s.get('spell_name', '') for s in counter_spells if s.get('spell_name'))
        counter_step = TimelineStep(
            kind='counter',
            title='Counter Spell',
            owner=counter_owner,
            icon_kind='spell',
            icon_payload=first.get('spell_name'),
            sub_icons=tuple(s.get('spell_name') for s in counter_spells[1:]),
            completed=True,
            active=False,
            interactive=False,
            primary_action=None,
            tone='warning',
            info_headline=f'{counter_owner.title()} cast {counter_names or "a counter spell"}',
            info_body=' '.join(
                _prelude_effect_line(spell, own=counter_own)
                for spell in counter_spells
            ) or 'The counter spell resolved.',
            info_assets=_prelude_info_assets(
                counter_spells,
                own=counter_own,
                field_screen=field_screen,
                game=game,
            ),
            replay_key=_spell_replay_key('counter', first),
        )
        steps.append(counter_step)

    # 5) Defender --------------------------------------------------------
    defender_second_active = bool(
        advancing_id
        and _civil_war_pick_flow_active(game)
        and _get(game, 'civil_war_defender_second', False)
    )
    defender_select_active = bool(
        pending_defender_select_turn
        or pending_own_defender_select
        or defender_second_active
    )
    defender_pending_local = (
        bool(_get(field_screen, 'figure_pending_defender_selection'))
        or bool(_get(field_screen, 'figure_pending_own_defender_selection'))
        if field_screen is not None else False
    )
    defender_done = bool(defending_id) and not defender_second_active
    local_turn = bool(
        _get(game, 'turn', False)
        or (_get(game, 'turn_player_id', None) is not None
            and _same_identity(_get(game, 'turn_player_id', None), player_id))
    )
    defender_response_open = bool(
        advancing_id
        and advancing_player_id
        and not defending_id
        and not battle_confirmed
        and not battle_started
        and not attacker_second_active
        and not defender_second_active
        and not defender_select_active
        and not defender_pending_local
    )
    defender_response_for_you = bool(
        defender_response_open
        and not _same_identity(advancing_player_id, player_id)
        and local_turn
    )
    defender_response_waiting = bool(
        defender_response_open
        and _same_identity(advancing_player_id, player_id)
        and not local_turn
    )
    defender_response_active = defender_response_for_you or defender_response_waiting
    invader_swap = bool(
        pending_own_defender_select
        or (defender_second_active and own_is_attacker is False)
    )
    defender_owner = ''
    if invader_swap:
        defender_owner = 'you'
    elif defender_done:
        defender_owner = opp_name if own_is_attacker else 'you'
    elif pending_defender_select_turn:
        defender_owner = opp_name
    elif defender_response_for_you:
        defender_owner = 'you'
    elif defender_response_waiting:
        defender_owner = opp_name
    else:
        defender_owner = opp_name if own_is_attacker else 'you'
    defender_figure = _figure_by_id(field_screen, defending_id) if defending_id else None
    defender_figure_2 = _figure_by_id(field_screen, defending_id_2) if defending_id_2 else None
    defender_pending_figure = None
    if field_screen is not None:
        defender_pending_figure = (_get(field_screen, 'figure_pending_defender_selection')
                                   or _get(field_screen, 'figure_pending_own_defender_selection'))
    defender_asset_figure = defender_pending_figure or defender_figure
    defender_visible_after_attacker = attacker_done or attacker_pending_advance_local
    defender_side = 'opponent' if (own_is_attacker and not invader_swap) else 'own'
    defender_reveal = bool(defender_side == 'own' or battle_started or
                           _figure_is_revealed(field_screen, defender_asset_figure))
    defender_second_reveal = bool(defender_side == 'own' or battle_started or
                                  _figure_is_revealed(field_screen, defender_figure_2))
    defender_info_assets = _figure_assets((
        (defender_figure, defender_side, bool(defender_side == 'own' or battle_started or
                                             _figure_is_revealed(field_screen, defender_figure))),
        (defender_figure_2, defender_side, defender_second_reveal),
        (defender_pending_figure, defender_side, defender_reveal),
    ))
    # A single-option opponent defender is auto-selected (no real choice), so it
    # must not be labelled "Chosen by you".
    defender_auto_selected = bool(
        defending_id is not None
        and defending_id == _get(field_screen, '_auto_selected_defender_id', None)
    )
    defender_chosen_by_player = bool(
        own_is_attacker
        and not invader_swap
        and not defender_auto_selected
        and (
            defender_pending_local
            or _defender_selected_by_player(
                game, field_screen, defending_id, player_id)
        )
    )
    defender_sidenote = (
        'Chosen by you' if defender_chosen_by_player
        else 'Invader Swap' if invader_swap
        else 'Civil War' if defender_second_active or defending_id_2
        else 'Response' if defender_response_active
        else ''
    )
    defender_step = TimelineStep(
        kind='defender',
        title='Defending Figure',
        owner=defender_owner,
        icon_kind='figure' if defender_figure else 'none',
        icon_payload={
            'figure': defender_figure,
            'side': defender_side,
            'reveal': defender_reveal,
        } if defender_figure else None,
        completed=defender_done and not defender_pending_local,
        active=(
            defender_select_active
            or defender_pending_local
            or defender_response_active
        ) and defender_visible_after_attacker,
        interactive=(
            defender_select_active
            or defender_pending_local
            or defender_response_for_you
        ),
        primary_action=(
            'confirm' if defender_pending_local
            else 'select_second' if defender_second_active
            else 'select_defender' if defender_select_active
            else 'respond_advance' if defender_response_for_you
            else None
        ),
        tone=(
            'action' if (defender_select_active or defender_pending_local or defender_response_for_you)
            else 'waiting' if defender_response_waiting
            else 'good' if defender_done else 'neutral'
        ),
        sidenote=defender_sidenote,
        info_headline=(
            'Confirm opponent defender' if defender_pending_local and defender_chosen_by_player
            else 'Confirm the second defender' if defender_pending_local and defender_second_active
            else 'Confirm the defender' if defender_pending_local
            else 'Choose your second Civil War defender' if defender_second_active and invader_swap
            else 'Pick the second Civil War defender' if defender_second_active
            else 'Pick the defender' if defender_select_active
            else 'Respond to the advance' if defender_response_for_you
            else 'Defender response' if defender_response_waiting
            else 'Opponent defender chosen by you' if defender_done and defender_chosen_by_player
            else 'Defender locked in' if defender_done
            else 'Awaiting defender'
        ),
        info_body=(
            ('Press Confirm to commit, or Cancel to pick another figure. '
             'This is the opponent battle figure you selected.')
            if defender_pending_local and defender_chosen_by_player
            else 'Press Confirm to commit, or Cancel to pick another figure.'
            if defender_pending_local
            else (
                'Select another of your own village figures of the same color.'
                if defender_second_active and invader_swap
                else 'Select another defender village figure of the same color.'
                if defender_second_active
                else
                'Select one of your own figures to defend (Invader Swap).'
                if invader_swap and defender_select_active
                else 'Select the opponent figure that will fight your advance.'
                if defender_select_active and own_is_attacker
                else 'You selected this opponent figure to fight your advance.'
                if defender_done and defender_chosen_by_player
                else 'Counter-advance with a legal figure, use your configured counter spell, or spend your turn.'
                if defender_response_for_you
                else f'Waiting for {opp_name} to counter-advance, use a counter spell, or spend the turn.'
                if defender_response_waiting
                else 'Counter-advance with a legal figure or spend your turn.'
                if defender_select_active
                else ''
            )
        ),
        info_assets=defender_info_assets,
    )
    steps.append(defender_step)

    # 6) To battle -------------------------------------------------------
    to_battle_active = (
        defender_done and attacker_done and not battle_confirmed
        and not _get(game, 'battle_moves_phase', False)
        and not attacker_second_active
        and not defender_second_active
    )
    to_battle_step = TimelineStep(
        kind='to_battle',
        title='To Battle!',
        icon_kind='go',
        completed=battle_confirmed,
        active=(to_battle_active or (
            _get(game, 'battle_moves_phase', False)
            and not battle_confirmed
            and not attacker_second_active
            and not defender_second_active
        )),
        interactive=False,
        primary_action=None,
        tone='action' if to_battle_active else 'good' if battle_confirmed else 'neutral',
        info_headline='Battle imminent' if to_battle_active else 'Battle in progress',
        info_body='Both fighters are chosen \u2014 the duel is about to begin.'
                  if to_battle_active
                  else 'The duel is unfolding on the battlefield \u2014 watch the rounds resolve.',
    )
    steps.append(to_battle_step)

    # If the battle has started or finished, no step is "active" in the
    # interactive sense — collapse to all-completed to freeze the timeline.
    if battle_started or _get(game, 'game_over', False) or _get(game, 'state', None) == 'finished':
        for step in steps:
            step.active = False
            step.completed = True
            step.interactive = False
            step.primary_action = None
        # Final info: battle in progress or finished.
        steps[-1].active = False

    # Ensure exactly one step is active (or none).  Pick the leftmost
    # incomplete-and-active candidate; clear `active` from later ones.
    seen_active = False
    for step in steps:
        if step.active and not seen_active:
            seen_active = True
        elif step.active and seen_active:
            step.active = False
        # Steps before the active one are by definition completed unless
        # they are explicitly skipped (icon_kind == 'none' and not active).
        # We don't auto-mark them so the panel can render "no spell"
        # silhouettes.
    return steps
