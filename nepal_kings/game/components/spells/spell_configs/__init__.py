"""
Spell configurations module.

Import all spell configurations here and add them to SPELL_CONFIG_LIST.
The SpellManager will automatically load all spells from this list.
"""

# Import your spell configs here
# from .example_spell_config import EXAMPLE_SPELL_CONFIGS
# from .combat_spells_config import COMBAT_SPELL_CONFIGS
# from .utility_spells_config import UTILITY_SPELL_CONFIGS
from .ability_spell_config import ALL_ABILITY_CONFIGS
from .battle_spell_config import ALL_BATTLE_CONFIGS
from .instant_spell_config import ALL_INSTANT_CONFIGS

# Combine all spell configs into a single list
SPELL_CONFIG_LIST = [
    # Add your spell configs here
    # Example:
    # *EXAMPLE_SPELL_CONFIGS,
    # *COMBAT_SPELL_CONFIGS,
    # *UTILITY_SPELL_CONFIGS,
    *ALL_ABILITY_CONFIGS,
    *ALL_BATTLE_CONFIGS,
    *ALL_INSTANT_CONFIGS,
]

# When you create actual spell configs, uncomment and import them above
# For now, this list is empty to prevent errors
