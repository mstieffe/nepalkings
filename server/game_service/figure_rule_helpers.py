# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared figure legality helpers for battle participation rules."""

_BATTLE_VILLAGE_ONLY_MODIFIERS = frozenset({'Peasant War', 'Civil War'})
_BATTLE_CASTLE_ONLY_MODIFIERS = frozenset({'Royal Decree'})

# Modifier spells that restrict which battlefield the fighters come from.
BATTLE_FIELD_MODIFIER_SPELLS = (
    _BATTLE_VILLAGE_ONLY_MODIFIERS | _BATTLE_CASTLE_ONLY_MODIFIERS
)


def figure_has_family_skill(figure, skill_name):
    """Return True when a runtime/config figure has a stored or family skill."""
    if not figure:
        return False
    if bool(getattr(figure, skill_name, False)):
        return True
    try:
        from ai.figure_recipes import FAMILY_SKILLS
        skills = FAMILY_SKILLS.get(figure.family_name) or FAMILY_SKILLS.get(figure.name) or {}
        return bool(skills.get(skill_name))
    except Exception:
        return False


def _modifier_type(modifier):
    if isinstance(modifier, dict):
        return modifier.get('type')
    if isinstance(modifier, str):
        return modifier
    return None


def battle_required_field(modifiers):
    """Return the battlefield the active modifiers restrict fighters to.

    ``'castle'`` (Royal Decree), ``'village'`` (Peasant War / Civil War) or
    ``None`` when no field restriction applies.  Royal Decree has precedence
    over the village-only modifiers: castle-only beats village-only.
    """
    if isinstance(modifiers, dict):
        modifiers = [modifiers]
    if not isinstance(modifiers, (list, tuple)):
        return None
    types = {_modifier_type(mod) for mod in modifiers}
    if types & _BATTLE_CASTLE_ONLY_MODIFIERS:
        return 'castle'
    if types & _BATTLE_VILLAGE_ONLY_MODIFIERS:
        return 'village'
    return None


def modifiers_require_village(modifiers):
    """True when active/planned battle modifiers restrict fighters to villages."""
    return battle_required_field(modifiers) == 'village'


def figure_field_allowed(figure, modifiers):
    """True when *figure*'s field satisfies the modifiers' field restriction."""
    required = battle_required_field(modifiers)
    if not required:
        return True
    return (getattr(figure, 'field', None) or '') == required


def required_field_block_message(required_field, action='battle'):
    """Human-readable reason a figure of the wrong field cannot join battle."""
    if required_field == 'castle':
        return f'Royal Decree: only castle figures can {action}'
    if required_field == 'village':
        return 'This battle modifier requires village figures.'
    return None


def config_strategy_modifiers(cfg):
    """Return configured defence modifiers/prelude restrictions for validation."""
    modifiers = []
    prelude = getattr(cfg, 'prelude_spell_name', None)
    if prelude in BATTLE_FIELD_MODIFIER_SPELLS:
        modifiers.append({'type': prelude})
    legacy = getattr(cfg, 'battle_modifier', None)
    if legacy:
        if isinstance(legacy, list):
            modifiers.extend(mod for mod in legacy if isinstance(mod, dict))
        elif isinstance(legacy, dict):
            modifiers.append(legacy)
    return modifiers


def explain_counter_advance_block(figure, *, require_village=False, deficit=False,
                                  required_field=None):
    """Return a human-readable reason this figure cannot counter-advance."""
    if not figure:
        return 'Figure not found'
    if deficit:
        return 'Cannot select a figure with resource deficit'
    if figure_has_family_skill(figure, 'cannot_attack'):
        return 'This figure cannot counter-advance because it cannot attack.'
    if figure_has_family_skill(figure, 'cannot_defend'):
        return 'This figure cannot counter-advance because it cannot defend.'
    if required_field is None and require_village:
        required_field = 'village'
    if required_field and (getattr(figure, 'field', None) or '') != required_field:
        if required_field == 'castle':
            return 'Royal Decree: only castle figures can join the battle.'
        return 'This battle modifier requires village figures.'
    return None


def figure_can_counter_advance(figure, *, require_village=False, deficit=False,
                               required_field=None):
    return explain_counter_advance_block(
        figure,
        require_village=require_village,
        deficit=deficit,
        required_field=required_field,
    ) is None
