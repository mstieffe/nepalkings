# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared figure legality helpers for battle participation rules."""

_BATTLE_VILLAGE_ONLY_MODIFIERS = frozenset({'Peasant War', 'Civil War'})


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


def modifiers_require_village(modifiers):
    """True when active/planned battle modifiers restrict fighters to villages."""
    if isinstance(modifiers, dict):
        modifiers = [modifiers]
    if not isinstance(modifiers, (list, tuple)):
        return False
    return any(_modifier_type(mod) in _BATTLE_VILLAGE_ONLY_MODIFIERS for mod in modifiers)


def config_strategy_modifiers(cfg):
    """Return configured defence modifiers/prelude restrictions for validation."""
    modifiers = []
    prelude = getattr(cfg, 'prelude_spell_name', None)
    if prelude in _BATTLE_VILLAGE_ONLY_MODIFIERS:
        modifiers.append({'type': prelude})
    legacy = getattr(cfg, 'battle_modifier', None)
    if legacy:
        if isinstance(legacy, list):
            modifiers.extend(mod for mod in legacy if isinstance(mod, dict))
        elif isinstance(legacy, dict):
            modifiers.append(legacy)
    return modifiers


def explain_counter_advance_block(figure, *, require_village=False, deficit=False):
    """Return a human-readable reason this figure cannot counter-advance."""
    if not figure:
        return 'Figure not found'
    if deficit:
        return 'Cannot select a figure with resource deficit'
    if figure_has_family_skill(figure, 'cannot_attack'):
        return 'This figure cannot counter-advance because it cannot attack.'
    if figure_has_family_skill(figure, 'cannot_defend'):
        return 'This figure cannot counter-advance because it cannot defend.'
    if require_village and getattr(figure, 'field', None) != 'village':
        return 'This battle modifier requires village figures.'
    return None


def figure_can_counter_advance(figure, *, require_village=False, deficit=False):
    return explain_counter_advance_block(
        figure,
        require_village=require_village,
        deficit=deficit,
    ) is None
