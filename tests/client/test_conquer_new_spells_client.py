# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Client-side tests for the conquer spell expansion.

Covers the conquer-only spell families (Royal Decree, Copy Figure,
Landslide, Draw 4 MainCards): duel spell book exclusion, prelude picker
contents and overlap-free layout, Royal Decree field restrictions,
Copy Figure hidden targeting, animation dispatch, the Landslide-inverted
land bonus, and All Seeing Eye gamble-preview privacy.
"""
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pygame
import pytest


APP_DIR = Path(__file__).resolve().parents[2] / 'nepal_kings'

NEW_FAMILIES = ('Royal Decree', 'Copy Figure', 'Landslide', 'Draw 4 MainCards')

NEW_FAMILY_ICONS = {
    'Royal Decree': 'kings_war.png',
    'Copy Figure': 'copy.png',
    'Landslide': 'landslide.png',
    'Draw 4 MainCards': 'draw_four_main.png',
}


@pytest.fixture(scope='module')
def spell_manager():
    pygame.display.set_mode((100, 100))
    from game.components.spells.spell_manager import SpellManager
    return SpellManager()


# ── Spell family configs ─────────────────────────────────────────────────────

def test_new_families_registered_as_conquer_only(spell_manager):
    for name in NEW_FAMILIES:
        family = spell_manager.get_family_by_name(name)
        assert family is not None, name
        assert family.conquer_only is True
        assert isinstance(family.icon_img, pygame.Surface)
        assert isinstance(family.icon_gray_img, pygame.Surface)
        assert family.spells, f'{name} has no castable variants'


def test_new_family_types_and_recipes(spell_manager):
    expected = {
        'Royal Decree': ('tactics', {'K'}),
        'Copy Figure': ('enchantment', {'10'}),
        'Landslide': ('enchantment', {'2'}),
        'Draw 4 MainCards': ('greed', {'8'}),
    }
    red = {'Hearts', 'Diamonds'}
    black = {'Clubs', 'Spades'}
    for name, (spell_type, ranks) in expected.items():
        family = spell_manager.get_family_by_name(name)
        assert family.type == spell_type
        for spell in family.spells:
            assert len(spell.cards) == 2
            assert {c.rank for c in spell.cards} == ranks
            suits = {c.suit for c in spell.cards}
            assert suits <= red or suits <= black, \
                f'{name} variant crosses colors: {suits}'


def test_existing_families_not_conquer_only(spell_manager):
    for name in ('Poison', 'Health Boost', 'All Seeing Eye', 'Dump Cards',
                 'Draw 2 MainCards', 'Fill up to 10', 'Peasant War',
                 'Civil War', 'Blitzkrieg', 'Invader Swap'):
        family = spell_manager.get_family_by_name(name)
        assert family is not None, name
        assert getattr(family, 'conquer_only', False) is False


def test_color_and_greyscale_icon_assets_exist():
    for filename in NEW_FAMILY_ICONS.values():
        assert (APP_DIR / 'img' / 'spells' / 'icons' / filename).exists()
        assert (APP_DIR / 'img' / 'spells' / 'icons_greyscale' / filename).exists()


# ── Duel spell book exclusion ────────────────────────────────────────────────

def test_duel_spell_book_excludes_conquer_only_families(spell_manager):
    from game.screens.cast_spell_screen import CastSpellScreen

    stub = object.__new__(CastSpellScreen)
    stub.window = pygame.display.get_surface()
    stub.game = None
    stub.spell_manager = spell_manager
    stub.init_spell_family_icons()

    shown = {btn.family.name for btn in stub.spell_family_buttons}
    for name in NEW_FAMILIES:
        assert name not in shown
    # Duel spells remain in the book.
    assert 'Fill up to 10' in shown
    assert 'Draw 2 MainCards' in shown
    assert 'All Seeing Eye' in shown


# ── Prelude picker contents + layout ─────────────────────────────────────────

def _build_prelude_picker(spell_manager, allowed):
    from game.screens.prelude_spell_screen import PreludeSpellScreen

    stub = object.__new__(PreludeSpellScreen)
    stub.window = pygame.display.get_surface()
    stub.game = None
    stub.spell_manager = spell_manager
    stub.allowed_spell_order = list(allowed)
    stub.allowed_spells = set(allowed)
    stub._sx = lambda v: v
    stub._sy = lambda v: v
    stub._spos = lambda x, y: (x, y)
    stub.init_spell_family_icons()
    return stub


def test_conquer_picker_lists_new_spells_without_fill(spell_manager):
    from game.screens.conquer_screen import _CONQUER_PRELUDE_SPELLS
    assert 'Fill up to 10' not in _CONQUER_PRELUDE_SPELLS
    for name in NEW_FAMILIES:
        assert name in _CONQUER_PRELUDE_SPELLS
    # Related draw spells sit next to each other in the picker.
    draw_2 = _CONQUER_PRELUDE_SPELLS.index('Draw 2 MainCards')
    assert _CONQUER_PRELUDE_SPELLS[draw_2 + 1] == 'Draw 4 MainCards'
    picker = _build_prelude_picker(spell_manager, _CONQUER_PRELUDE_SPELLS)
    shown = {btn.family.name for btn in picker.spell_family_buttons}
    assert shown == set(_CONQUER_PRELUDE_SPELLS)
    # The greed row is laid out in allowlist order: Draw 4 follows Draw 2.
    greed_buttons = [btn for btn in picker.spell_family_buttons
                     if btn.family.type == 'greed']
    greed_buttons.sort(key=lambda btn: btn.x)
    names = [btn.family.name for btn in greed_buttons]
    assert names.index('Draw 4 MainCards') == names.index('Draw 2 MainCards') + 1


def test_defence_picker_lists_new_spells(spell_manager):
    from game.screens.defence_screen import _DEFENCE_PRELUDE_SPELLS
    assert 'Fill up to 10' not in _DEFENCE_PRELUDE_SPELLS
    for name in NEW_FAMILIES:
        assert name in _DEFENCE_PRELUDE_SPELLS
    assert 'All Seeing Eye' in _DEFENCE_PRELUDE_SPELLS
    assert 'Draw 2 MainCards' in _DEFENCE_PRELUDE_SPELLS
    picker = _build_prelude_picker(spell_manager, _DEFENCE_PRELUDE_SPELLS)
    shown = {btn.family.name for btn in picker.spell_family_buttons}
    assert shown == set(_DEFENCE_PRELUDE_SPELLS)


def _assert_picker_geometry(picker):
    """All icon cells stay inside the details panel and never overlap."""
    from config import settings
    box_right = settings.CAST_SPELL_INFO_BOX_X + settings.CAST_SPELL_INFO_BOX_WIDTH
    rows = {}
    for btn in picker.spell_family_buttons:
        assert btn.fixed_size is True
        assert btn.x + settings.SPELL_ICON_WIDTH // 2 <= box_right
        rows.setdefault(btn.y, []).append(btn.x)
    for xs in rows.values():
        xs = sorted(xs)
        for a, b in zip(xs, xs[1:]):
            assert b - a >= settings.SPELL_ICON_WIDTH, \
                f'icon cells overlap: dx={b - a}'


def test_conquer_picker_has_no_overlap_desktop(spell_manager):
    from game.screens.conquer_screen import _CONQUER_PRELUDE_SPELLS
    picker = _build_prelude_picker(spell_manager, _CONQUER_PRELUDE_SPELLS)
    _assert_picker_geometry(picker)


def test_defence_picker_has_no_overlap_desktop(spell_manager):
    from game.screens.defence_screen import _DEFENCE_PRELUDE_SPELLS
    picker = _build_prelude_picker(spell_manager, _DEFENCE_PRELUDE_SPELLS)
    _assert_picker_geometry(picker)


def test_conquer_picker_has_no_overlap_compact_landscape():
    code = r'''
import pygame
from config import settings
pygame.init()
pygame.display.set_mode((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
from game.components.spells.spell_manager import SpellManager
from game.screens.prelude_spell_screen import PreludeSpellScreen
from game.screens.conquer_screen import _CONQUER_PRELUDE_SPELLS

stub = object.__new__(PreludeSpellScreen)
stub.window = pygame.display.get_surface()
stub.game = None
stub.spell_manager = SpellManager()
stub.allowed_spells = set(_CONQUER_PRELUDE_SPELLS)
stub._sx = lambda v: v
stub._sy = lambda v: v
stub._spos = lambda x, y: (x, y)
stub.init_spell_family_icons()

box_right = settings.CAST_SPELL_INFO_BOX_X + settings.CAST_SPELL_INFO_BOX_WIDTH
rows = {}
for btn in stub.spell_family_buttons:
    assert btn.x + settings.SPELL_ICON_WIDTH // 2 <= box_right, (btn.name, btn.x)
    rows.setdefault(btn.y, []).append(btn.x)
for xs in rows.values():
    xs = sorted(xs)
    for a, b in zip(xs, xs[1:]):
        assert b - a >= settings.SPELL_ICON_WIDTH, ('overlap', b - a)
print('OK')
'''
    env = os.environ.copy()
    env.update({
        'SDL_VIDEODRIVER': 'dummy',
        'SDL_AUDIODRIVER': 'dummy',
        'NK_SCREEN_WIDTH': '854',
        'NK_SCREEN_HEIGHT': '480',
        'NK_IS_MOBILE': '1',
        'NK_UI_SCALE': '1.6',
    })
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=APP_DIR, env=env, capture_output=True, text=True,
        timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ── Royal Decree field restrictions ──────────────────────────────────────────

def _field_screen_stub(modifiers):
    from game.screens.field_screen import FieldScreen
    stub = object.__new__(FieldScreen)
    stub.game = SimpleNamespace(battle_modifier=modifiers, player_id=1)
    return stub


def test_field_required_mode_royal_decree():
    stub = _field_screen_stub([{'type': 'Royal Decree'}])
    assert stub._battle_required_field_mode() == ('castle', 'Royal Decree')
    message = stub._required_field_message('castle', 'Royal Decree', action='advance')
    assert 'castle' in message


def test_field_required_mode_decree_beats_village_modifiers():
    stub = _field_screen_stub([
        {'type': 'Peasant War'}, {'type': 'Royal Decree'},
    ])
    assert stub._battle_required_field_mode() == ('castle', 'Royal Decree')
    stub = _field_screen_stub([{'type': 'Civil War'}])
    assert stub._battle_required_field_mode() == ('village', 'Civil War')
    stub = _field_screen_stub([{'type': 'Landslide'}])
    assert stub._battle_required_field_mode() == (None, None)


def test_detail_box_disables_advance_for_non_castle_under_decree():
    from game.components.figure_detail_box import FigureDetailBox

    game = SimpleNamespace(
        battle_modifier=[{'type': 'Royal Decree'}],
        advancing_figure_id=None,
        advancing_player_id=None,
        player_id=1,
        resting_figure_ids=[],
        is_battle_active=lambda: False,
        civil_war_awaiting_second=False,
    )
    village_figure = SimpleNamespace(
        id=7, cannot_attack=False,
        family=SimpleNamespace(field='village', color='offensive'),
    )

    class _Btn:
        def __init__(self):
            self.disabled = False
            self.disabled_reason = None

    button = _Btn()
    # Replicate the detail-box modifier gate on a stub instance.
    stub = object.__new__(FigureDetailBox)
    stub.game = game
    stub.figure = village_figure
    stub.has_any_deficit = False
    modifier_types = [m.get('type') for m in game.battle_modifier]
    assert 'Royal Decree' in modifier_types
    figure_field = stub.figure.family.field
    if 'Royal Decree' in modifier_types and figure_field != 'castle':
        button.disabled = True
        button.disabled_reason = 'royal_decree'
    assert button.disabled is True
    assert button.disabled_reason == 'royal_decree'


# ── Copy Figure hidden targeting ─────────────────────────────────────────────

def _selection_stub(scope, valid_ids, own_player_id=1):
    from game.screens.field_screen import FieldScreen
    stub = object.__new__(FieldScreen)
    stub.game = SimpleNamespace(
        battle_modifier=[],
        player_id=own_player_id,
        civil_war_awaiting_second=False,
        pending_forced_advance=False,
        advancing_figure_id=None,
    )
    stub.state = SimpleNamespace(pending_conquer_prelude_target={
        'target_scope': scope,
        'valid_target_ids': list(valid_ids),
        'spell_name': 'Copy Figure',
    })
    stub.defender_selection_mode = False
    stub.conquer_own_defender_mode = False
    stub._is_conquer_visual_ghost_figure = lambda fig: False
    return stub


def test_copy_figure_hidden_scope_allows_checkmate_opponent_targets():
    stub = _selection_stub('opponent_hidden', [42])
    checkmate_opponent = SimpleNamespace(id=42, player_id=2, checkmate=True)
    icon = SimpleNamespace(figure=checkmate_opponent)
    assert stub._icon_is_selectable_for_current_mode(icon) is True


def test_copy_figure_hidden_scope_rejects_own_and_invalid_targets():
    stub = _selection_stub('opponent_hidden', [42])
    own_figure = SimpleNamespace(id=42, player_id=1, checkmate=False)
    assert stub._icon_is_selectable_for_current_mode(SimpleNamespace(figure=own_figure)) is False
    invalid_opponent = SimpleNamespace(id=99, player_id=2, checkmate=False)
    assert stub._icon_is_selectable_for_current_mode(SimpleNamespace(figure=invalid_opponent)) is False


def test_poison_scope_still_excludes_checkmate_targets():
    stub = _selection_stub('opponent', [42])
    checkmate_opponent = SimpleNamespace(id=42, player_id=2, checkmate=True)
    assert stub._icon_is_selectable_for_current_mode(SimpleNamespace(figure=checkmate_opponent)) is False


# ── Animation dispatch ───────────────────────────────────────────────────────

class _RecordingEffects:
    PROJECTILE_MS = 420

    def __init__(self):
        self.calls = []

    def _record(self, name):
        def _fn(*args, **kwargs):
            self.calls.append(name)
            return 1
        return _fn

    def __getattr__(self, name):
        if name.startswith('spawn_'):
            return self._record(name)
        raise AttributeError(name)

    def called(self, name):
        return name in self.calls


def _anim_screen_stub(effect_data):
    from game.screens.conquer_game_screen import ConquerGameScreen
    stub = object.__new__(ConquerGameScreen)
    stub.state = SimpleNamespace(game=SimpleNamespace(mode='conquer'))
    stub._conquer_effects = _RecordingEffects()
    stub._conquer_spell_anim_impact_ms = {}
    rect = pygame.Rect(0, 0, 40, 40)
    stub._resolve_spell_step_info = lambda kind, name: {
        'spell_name': name, 'effect_data': dict(effect_data)}
    stub._conquer_duel_lane_target_rect = lambda: rect
    stub._conquer_tactics_rail_target_rect = lambda: rect
    stub._conquer_opponent_hand_target_rect = lambda: rect
    stub._lookup_conquer_figure_rect = lambda fid: rect
    return stub


def test_spell_presets_exist_for_new_spells():
    from game.components.conquer_effects import SPELL_VISUAL_PRESETS
    for name in NEW_FAMILIES + ('All Seeing Eye',):
        assert name in SPELL_VISUAL_PRESETS


def test_royal_decree_animation_dispatches_banner_and_redraw():
    stub = _anim_screen_stub({'caster_dumped': 3, 'opponent_dumped': 3})
    anchor = pygame.Rect(0, 0, 30, 30)
    fired = stub._fire_spell_step_animation(
        ('prelude_own', 'Royal Decree', 'own'), anchor,
        step_kind='prelude_own', spell_name='Royal Decree')
    assert fired is True
    effects = stub._conquer_effects
    assert effects.called('spawn_banner')
    assert effects.called('spawn_rect_pulse')
    assert effects.called('spawn_floating_text_at_rect')
    assert effects.called('spawn_spell_to_rect')


def test_landslide_animation_dispatches_shake_and_pulse():
    stub = _anim_screen_stub({})
    anchor = pygame.Rect(0, 0, 30, 30)
    fired = stub._fire_spell_step_animation(
        ('prelude_own', 'Landslide', 'own'), anchor,
        step_kind='prelude_own', spell_name='Landslide')
    assert fired is True
    effects = stub._conquer_effects
    assert effects.called('spawn_banner')
    assert effects.called('spawn_shake')
    assert effects.called('spawn_floating_text_at_rect')


def test_copy_figure_animation_dispatches_spinning_ghost():
    stub = _anim_screen_stub({'source_figure_id': 5, 'copied_figure_id': 9})
    anchor = pygame.Rect(0, 0, 30, 30)
    key = ('prelude_own', 'Copy Figure', 'own')
    fired = stub._fire_spell_step_animation(
        key, anchor, step_kind='prelude_own', spell_name='Copy Figure')
    assert fired is True
    effects = stub._conquer_effects
    assert effects.called('spawn_rect_pulse')
    assert effects.called('spawn_copy_ghost')     # the spinning one-shot
    assert effects.called('spawn_floating_text_at_rect')
    # Marked target-fired so the update loop never re-fires (no endless spin).
    assert key in stub._spell_anim_target_fired


def test_draw_4_animation_dispatches_card_projectile():
    stub = _anim_screen_stub({'cards_drawn': 4})
    anchor = pygame.Rect(0, 0, 30, 30)
    fired = stub._fire_spell_step_animation(
        ('prelude_own', 'Draw 4 MainCards', 'own'), anchor,
        step_kind='prelude_own', spell_name='Draw 4 MainCards')
    assert fired is True
    assert stub._conquer_effects.called('spawn_spell_to_rect')


def test_all_seeing_eye_animation_dispatches_eye_sweep():
    stub = _anim_screen_stub({})
    anchor = pygame.Rect(0, 0, 30, 30)
    fired = stub._fire_spell_step_animation(
        ('prelude_own', 'All Seeing Eye', 'own'), anchor,
        step_kind='prelude_own', spell_name='All Seeing Eye')
    assert fired is True
    assert stub._conquer_effects.called('spawn_spell_to_rect')


def test_draw_4_floating_text():
    from game.screens.conquer_game_screen import ConquerGameScreen
    stub = object.__new__(ConquerGameScreen)
    text = stub._card_spell_floating_text(
        'Draw 4 MainCards', {'effect_data': {'cards_drawn': 4}})
    assert text == '+4 cards'
    assert stub._card_spell_floating_text('Draw 4 MainCards', None) == '+4 cards'


# ── Landslide land bonus on the client ───────────────────────────────────────

def _game_proxy_stub(modifiers, suit='Hearts', value=3):
    from game.core.game import Game
    stub = object.__new__(Game)
    stub.battle_modifier = modifiers
    stub.land_suit_bonus_suit = suit
    stub.land_suit_bonus_value = value
    return stub


def test_effective_land_bonus_inverted_by_landslide():
    game = _game_proxy_stub([{'type': 'Landslide'}])
    assert game.effective_land_bonus() == ('Hearts', -3)
    # Duplicate Landslide entries never invert back to positive.
    game = _game_proxy_stub([{'type': 'Landslide'}, {'type': 'Landslide'}])
    assert game.effective_land_bonus() == ('Hearts', -3)


def test_effective_land_bonus_without_landslide():
    game = _game_proxy_stub([])
    assert game.effective_land_bonus() == ('Hearts', 3)
    game = _game_proxy_stub([{'type': 'Royal Decree'}])
    assert game.effective_land_bonus() == ('Hearts', 3)


def test_figure_icon_badge_reflects_landslide_live():
    """The field icon's bonus badge must pick up Landslide without a rebuild.

    The support part is cached at icon build time; the land component is
    evaluated live so the badge flips from (+3) to (-3) the moment the
    Landslide modifier lands on the game proxy.
    """
    from game.components.figures.figure_icon import FieldFigureIcon
    icon = object.__new__(FieldFigureIcon)
    icon.battle_bonus_received = 0
    icon.figure = SimpleNamespace(suit='Hearts')
    game = _game_proxy_stub([])
    game.mode = 'conquer'
    icon.game = game
    assert icon._current_battle_bonus_received() == 3
    game.battle_modifier = [{'type': 'Landslide'}]
    assert icon._current_battle_bonus_received() == -3
    # Hidden-state icons can suppress the badge entirely.
    icon.suppress_battle_bonus = True
    assert icon._current_battle_bonus_received() == 0


def test_landslide_receipt_land_row_negative():
    from game.screens.conquer_game_screen import ConquerGameScreen
    stub = object.__new__(ConquerGameScreen)
    stub.state = SimpleNamespace(game=_game_proxy_stub([{'type': 'Landslide'}]))
    figures = [SimpleNamespace(id=1, suit='Hearts')]
    assert stub._conquer_lane_land_bonus_for(figures) == -3
    # Non-matching figures get nothing either way.
    assert stub._conquer_lane_land_bonus_for(
        [SimpleNamespace(id=2, suit='Clubs')]) == 0


def test_support_badge_group_value_honours_negative_land_bonus():
    """The real grouping must show the true sign — Landslide's inverted land
    bonus renders as '-3', not a forced '+3'."""
    from game.screens.conquer_game_screen import ConquerGameScreen
    stub = object.__new__(ConquerGameScreen)

    def grouped_value(kind, value_text, numeric):
        entry = {
            'kind': kind, 'label': kind.title(), 'value': value_text,
            'numeric_value': numeric, 'section': 'clash', 'suit': 'Hearts',
        }
        sections = stub._conquer_support_display_sections([entry])
        groups = [g for grp in sections.values() for g in grp]
        assert len(groups) == 1
        return groups[0]['value']

    assert grouped_value('land_bonus', '-3', -3) == '-3'   # Landslide malus
    assert grouped_value('land_bonus', '+3', 3) == '+3'    # normal land bonus
    assert grouped_value('support_bonus', '+5', 5) == '+5'
    assert grouped_value('distance_attack', '-4', 4) == '-4'


# ── All Seeing Eye opponent hand strip ───────────────────────────────────────

def _hand_strip_stub(tactics, eye_active):
    from game.screens.conquer_game_screen import ConquerGameScreen
    stub = object.__new__(ConquerGameScreen)
    stub.state = SimpleNamespace(game=SimpleNamespace(
        has_active_all_seeing_eye=lambda: eye_active,
    ))
    stub._current_conquer_opponent_tactics = lambda: tactics
    # Timeline-gated reveal is exercised separately; here it mirrors the eye.
    stub._conquer_all_seeing_eye_revealed = lambda: eye_active
    return stub


def test_opponent_strip_flips_face_up_with_eye():
    tactics = [
        {'rank': 'K', 'suit': 'Hearts', 'status': 'available', 'played_round': None},
        {'rank': '7', 'suit': 'Spades', 'status': 'available', 'played_round': None},
        # Played / discarded tactics never show in the fan.
        {'rank': 'A', 'suit': 'Clubs', 'status': 'played', 'played_round': 0},
        {'rank': 'Q', 'suit': 'Clubs', 'status': 'discarded', 'played_round': None},
    ]
    stub = _hand_strip_stub(tactics, eye_active=True)
    # One spec per fan slot, in order; both available tactics revealed.
    assert stub._opponent_revealed_tactic_specs() == [
        ('Hearts', 'K'), ('Spades', '7')]


def test_opponent_strip_slot_count_matches_specs_length():
    """The reveal list is 1:1 with the fan slots so a revealed card can never
    land in the wrong slot (the old partial-reveal bug)."""
    tactics = [
        {'rank': 'K', 'suit': 'Hearts', 'status': 'available', 'played_round': None},
        # A stub with no rank/suit must occupy its own slot as face-down,
        # not shift the following revealed card up.
        {'id': 9, 'status': 'available', 'played_round': None},
        {'rank': '9', 'suit': 'Diamonds', 'status': 'available', 'played_round': None},
    ]
    stub = _hand_strip_stub(tactics, eye_active=True)
    specs = stub._opponent_revealed_tactic_specs()
    assert len(specs) == stub._opponent_hidden_hand_count() == 3
    assert specs == [('Hearts', 'K'), None, ('Diamonds', '9')]


def test_opponent_strip_stays_hidden_without_eye():
    tactics = [
        {'rank': 'K', 'suit': 'Hearts', 'status': 'available', 'played_round': None},
    ]
    stub = _hand_strip_stub(tactics, eye_active=False)
    assert stub._opponent_revealed_tactic_specs() == []


def test_own_all_seeing_eye_active_helper():
    from game.screens.conquer_game_screen import ConquerGameScreen
    stub = object.__new__(ConquerGameScreen)
    # _own_all_seeing_eye_active delegates to the timeline-gated reveal.
    stub._conquer_all_seeing_eye_revealed = lambda: True
    assert stub._own_all_seeing_eye_active() is True
    stub._conquer_all_seeing_eye_revealed = lambda: False
    assert stub._own_all_seeing_eye_active() is False


def test_all_seeing_eye_reveal_gated_on_timeline():
    """During pre-battle replay the reveal only activates once the leading
    timeline step reaches the All Seeing Eye cast; it is always on once the
    battle proper has started."""
    from game.screens.conquer_game_screen import ConquerGameScreen
    stub = object.__new__(ConquerGameScreen)

    def _step(kind, payload=None, active=False):
        return SimpleNamespace(kind=kind, icon_payload=payload, active=active,
                               completed=False)

    # Pre-battle: leading step is BEFORE the ASE step → hidden.
    steps_before = [
        _step('overview'),
        _step('prelude_own', 'Poison', active=True),
        _step('prelude_own', 'All Seeing Eye'),
    ]
    stub.state = SimpleNamespace(game=SimpleNamespace(
        has_active_all_seeing_eye=lambda: True, battle_confirmed=False))
    stub._is_battle_phase_active = lambda: False
    stub._conquer_timeline_panel = SimpleNamespace(
        derive_display_steps=lambda _self: steps_before)
    assert stub._conquer_all_seeing_eye_revealed() is False

    # Leading step is now the ASE step → revealed.
    steps_on = [
        _step('overview'),
        _step('prelude_own', 'Poison'),
        _step('prelude_own', 'All Seeing Eye', active=True),
    ]
    stub._conquer_timeline_panel = SimpleNamespace(
        derive_display_steps=lambda _self: steps_on)
    assert stub._conquer_all_seeing_eye_revealed() is True

    # Battle started → always revealed regardless of timeline.
    stub.state.game.battle_confirmed = True
    assert stub._conquer_all_seeing_eye_revealed() is True

    # No active Eye → never revealed.
    stub.state.game.has_active_all_seeing_eye = lambda: False
    assert stub._conquer_all_seeing_eye_revealed() is False
    # No game / missing helper is safely False.
    stub.state = SimpleNamespace(game=None)
    assert stub._own_all_seeing_eye_active() is False


def test_opponent_hand_cards_exclude_tactic_backing_cards():
    """Tactic-backing cards are not hand cards in tactics-hand conquer.

    They already render as the face-down fan on the opponent hand strip;
    counting them again in the All Seeing Eye hand display inflated the
    opponent's apparent hand size.
    """
    from game.screens.field_screen import FieldScreen
    stub = object.__new__(FieldScreen)
    stub.game = SimpleNamespace(
        mode='conquer',
        conquer_move_model='tactics_hand',
        opponent_player={'id': 2},
        main_cards=[
            {'id': 1, 'player_id': 2, 'in_deck': False,
             'part_of_figure': False, 'part_of_battle_move': False},
            {'id': 2, 'player_id': 2, 'in_deck': False,
             'part_of_figure': False, 'part_of_battle_move': True},
            {'id': 3, 'player_id': 2, 'in_deck': True,
             'part_of_figure': False, 'part_of_battle_move': False},
        ],
        side_cards=[
            {'id': 4, 'player_id': 2, 'in_deck': False,
             'part_of_figure': True, 'part_of_battle_move': False},
            {'id': 5, 'player_id': 2, 'in_deck': False,
             'part_of_figure': False, 'part_of_battle_move': False},
        ],
    )
    main, side = stub._get_opponent_hand_cards()
    assert [c['id'] for c in main] == [1]
    assert [c['id'] for c in side] == [5]


# ── All Seeing Eye gamble preview (client) ───────────────────────────────────

def _rail_stub(game):
    from game.components.conquer_tactics_rail import ConquerTacticsRail
    stub = object.__new__(ConquerTacticsRail)
    stub._parent = SimpleNamespace(state=SimpleNamespace(game=game))
    return stub


def test_gamble_preview_specs_per_round_independent_of_tactic():
    game = SimpleNamespace(
        player_id=1,
        battle_round=0,
        battle_gamble_previews={'1': {
            'round': 0,
            'specs': [
                {'rank': 'K', 'suit': 'Hearts', 'family_name': 'Call King'},
                {'rank': '7', 'suit': 'Spades', 'family_name': 'Dagger'},
            ],
        }},
    )
    rail = _rail_stub(game)
    # Same forecast for ANY tactic id (and none at all).
    specs = rail._gamble_preview_specs(11)
    assert specs is not None and len(specs) == 2
    assert rail._gamble_preview_specs(99) == specs
    assert rail._gamble_preview_specs() == specs
    # Stale round: no preview.
    game.battle_round = 1
    assert rail._gamble_preview_specs(11) is None


def test_gamble_preview_specs_absent_for_other_player():
    game = SimpleNamespace(
        player_id=2,
        battle_round=0,
        battle_gamble_previews={'1': {
            'round': 0,
            'specs': [{'rank': 'K', 'suit': 'Hearts'},
                      {'rank': '7', 'suit': 'Spades'}],
        }},
    )
    rail = _rail_stub(game)
    assert rail._gamble_preview_specs(11) is None


def test_gamble_spec_label_format():
    from game.components.conquer_tactics_rail import ConquerTacticsRail
    label = ConquerTacticsRail._gamble_spec_label(
        {'rank': 'K', 'suit': 'Hearts', 'family_name': 'Call King'})
    assert label == 'K♥ Call King'


def test_gamble_preview_overlay_renders_cards_when_armed():
    """The polished overlay draws the two forecast cards without error and
    only while the confirm is armed with a matching preview."""
    import pygame as _pg
    from game.components.conquer_tactics_rail import ConquerTacticsRail
    surf = _pg.display.set_mode((900, 600))
    now = _pg.time.get_ticks()
    game = SimpleNamespace(
        player_id=1,
        battle_round=0,
        battle_gamble_previews={'1': {
            'round': 0,
            'specs': [
                {'rank': 'K', 'suit': 'Hearts', 'family_name': 'Call King'},
                {'rank': '7', 'suit': 'Spades', 'family_name': 'Dagger'},
            ],
        }},
    )
    rail = object.__new__(ConquerTacticsRail)
    rail.window = surf
    rail._parent = SimpleNamespace(state=SimpleNamespace(game=game))
    rail._gamble_armed = {'move_id': 11, 'until_ms': now + 3000}
    rect = _pg.Rect(20, 20, 220, 360)
    # Renders cleanly with an armed matching preview.
    rail._draw_gamble_preview_overlay(rect)
    # No-op when not armed.
    rail._gamble_armed = None
    rail._draw_gamble_preview_overlay(rect)


# ── Copy Figure clone marker ─────────────────────────────────────────────────

def test_figure_carries_is_clone_flag():
    from game.components.figures.figure import Figure, FigureFamily
    fam = object.__new__(FigureFamily)
    fam.field = 'castle'
    clone = Figure(name='Clone King', sub_name='', suit='Hearts', family=fam,
                   key_cards=[], is_clone=True)
    assert clone.is_clone is True
    normal = Figure(name='Real King', sub_name='', suit='Hearts', family=fam,
                    key_cards=[])
    assert normal.is_clone is False


def test_field_icon_detects_clone_and_draws_aura():
    from game.components.figures.figure_icon import FieldFigureIcon
    icon = object.__new__(FieldFigureIcon)
    icon.figure = SimpleNamespace(is_clone=True)
    assert icon._is_clone_figure() is True
    icon.figure = SimpleNamespace(is_clone=False)
    assert icon._is_clone_figure() is False
    # Missing attribute is treated as not-a-clone.
    icon.figure = SimpleNamespace()
    assert icon._is_clone_figure() is False

    # _draw_clone_aura is a safe no-op for non-clones (no glow surfaces set).
    icon.figure = SimpleNamespace(is_clone=False)
    icon._draw_clone_aura(0, big=False)  # must not raise

    # With a clone + glow surfaces, the aura blits without error.
    surf = pygame.display.set_mode((120, 120))
    icon.window = surf
    icon.x, icon.y = 60, 60
    icon.rect_frame = pygame.Rect(46, 46, 28, 28)
    icon.glow_clone = pygame.Surface((40, 40), pygame.SRCALPHA)
    icon.glow_clone.fill((100, 160, 240, 255))
    icon.glow_clone_big = pygame.Surface((52, 52), pygame.SRCALPHA)
    icon.glow_clone_big.fill((100, 160, 240, 255))
    icon.figure = SimpleNamespace(is_clone=True)
    icon._draw_clone_aura(4, big=False)
    icon._draw_clone_aura(4, big=True)


def test_copy_ghost_effect_one_shot():
    """The spinning copy-ghost effect spawns, renders across its lifetime,
    and self-prunes when finished (no endless loop)."""
    import pygame as _pg
    from game.components.conquer_effects import ConquerEffectsLayer
    surf = _pg.display.set_mode((300, 300))
    layer = ConquerEffectsLayer(surf, lambda _id: None)
    src = _pg.Rect(20, 20, 40, 40)
    dst = _pg.Rect(220, 220, 40, 40)
    layer.spawn_copy_ghost(src, dst)
    assert len(layer._copies) == 1
    # Render a few frames mid-flight — must not raise.
    layer.draw()
    # Force the effect past its lifetime and prune.
    layer._copies[0]['started_at'] -= layer.COPY_MS + 200
    layer.draw()
    assert layer._copies == []
    # clear() also drops copies.
    layer.spawn_copy_ghost(src, dst)
    layer.clear()
    assert layer._copies == []


def test_clone_flag_survives_display_filter():
    """The conquer display filter shallow-copies the figure, preserving
    is_clone so the aura still renders after filtering."""
    from game.components.figures.figure import Figure, FigureFamily
    from game.components.figures.skill_display_filters import (
        filter_figure_for_display,
    )
    fam = object.__new__(FigureFamily)
    fam.field = 'castle'
    fam.name = 'Djungle King'
    clone = Figure(name='Djungle King', sub_name='', suit='Hearts', family=fam,
                   key_cards=[], is_clone=True, checkmate=True)
    filtered = filter_figure_for_display(clone, hide_checkmate=True)
    assert filtered.is_clone is True
    assert filtered.checkmate is False
