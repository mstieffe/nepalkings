# Spell System Documentation

## Overview

The spell system in Nepal Kings allows players to cast spells using cards from their hand. Spells work analogously to figures, with spell families and spell instances defined through configuration files.

## Architecture

### Core Components

1. **Spell** (`spell.py`): Individual spell instance with specific cards
2. **SpellFamily** (`spell.py`): Group of related spells with shared properties
3. **SpellManager** (`spell_manager.py`): Manages all spells and families
4. **SpellIcon** (`spell_icon.py`): UI component for displaying spells
5. **CastSpellScreen** (`cast_spell_screen.py`): Screen for casting spells

### Directory Structure

```
game/components/spells/
├── __init__.py
├── spell.py                    # Spell and SpellFamily classes
├── spell_icon.py               # SpellIcon UI components
├── spell_manager.py            # SpellManager
└── spell_configs/
    ├── __init__.py             # SPELL_CONFIG_LIST
    └── example_spell_config.py # Template/examples
```

## Spell Types

### Spell Type (Active/Passive)
- **Active**: Spells that have immediate, one-time effects
- **Passive**: Spells that persist and provide ongoing benefits

### Effect Type
- **Direct**: Immediate effects (e.g., draw cards, heal, damage)
- **Figure**: Attach to a figure and modify its properties
- **Battle**: Modify the upcoming battle mechanics

## Creating New Spells

### Step 1: Define Spell Configuration

Create a new config file in `spell_configs/` (e.g., `combat_spells_config.py`):

```python
from game.components.spells.spell import Spell
from game.components.cards.card import Card
from config import settings

def create_fireball_spells(family, suit):
    """Create Fireball spell instances."""
    spells = []
    
    # Example: 3-card spell with power scaling
    for rank in ['5', '6', '7', '8', '9', '10']:
        key_card_1 = Card(suit, 'K')
        key_card_2 = Card(suit, 'Q')
        number_card = Card(suit, rank)
        
        spell = Spell(
            name=f"Fireball (Power {rank})",
            family=family,
            cards=[key_card_1, key_card_2, number_card],
            suit=suit,
            key_cards=[key_card_1, key_card_2],
            number_card=number_card,
            requires_target=True,
            target_type='opponent_figure',
        )
        spells.append(spell)
    
    return spells

FIREBALL_CONFIG = {
    "name": "Fireball",
    "spell_type": "active",
    "effect_type": "instant",
    "description": "Deal damage to an opponent's figure",
    "suits": ["Diamonds", "Hearts", "Clubs", "Spades"],
    "icon_img": "fireball.png",
    "icon_gray_img": "fireball.png",
    "frame_img": "spell_frame.png",
    "frame_closed_img": "spell_frame.png",
    "frame_hidden_img": "spell_frame.png",
    "build_position": (
        settings.CAST_SPELL_ICON_START_X,
        settings.CAST_SPELL_ICON_START_Y
    ),
    "spells": create_fireball_spells,
}

COMBAT_SPELL_CONFIGS = [
    FIREBALL_CONFIG,
]
```

### Step 2: Register Configuration

Add to `spell_configs/__init__.py`:

```python
from .combat_spells_config import COMBAT_SPELL_CONFIGS

SPELL_CONFIG_LIST = [
    *COMBAT_SPELL_CONFIGS,
]
```

### Step 3: Implement Spell Logic

Extend the `Spell` class or create a subclass with custom `execute()` method:

```python
class FireballSpell(Spell):
    def execute(self, game, target=None):
        """Execute fireball spell."""
        if not target:
            return {'success': False, 'message': 'No target selected'}
        
        if not self.requires_target or self.target_type != 'opponent_figure':
            return {'success': False, 'message': 'Invalid target type'}
        
        # Get spell power from number card
        power = self.get_power()
        
        # TODO: Implement damage logic
        # - Reduce target figure's health/strength
        # - Remove figure if destroyed
        # - Update game state
        
        return {
            'success': True,
            'message': f'Dealt {power} damage to {target.name}'
        }
```

### Step 4: Create Images

Add spell images to the appropriate directories:
- `img/spells/icons/` - Colored spell icons
- `img/spells/icons_greyscale/` - Grayscale spell icons
- `img/spells/frames/` - Normal frames
- `img/spells/frames_greyscale/` - Greyscale frames (unbuildable)
- `img/spells/frames_hidden/` - Hidden frames (opponent spells)

## Spell Configuration Reference

### Required Fields

```python
{
    "name": str,              # Display name
    "spell_type": str,        # 'active' or 'passive'
    "effect_type": str,       # 'instant', 'ability', or 'battle'
    "description": str,       # What the spell does
    "suits": List[str],       # Available suits
    "icon_img": str,          # Icon filename
    "icon_gray_img": str,     # Grayscale icon filename
    "frame_img": str,         # Frame filename
    "frame_closed_img": str,  # Greyscale frame filename
    "frame_hidden_img": str,  # Hidden frame filename
    "spells": callable,       # Function(family, suit) -> List[Spell]
}
```

### Spell Instance Fields

```python
Spell(
    name=str,                    # Instance name
    family=SpellFamily,          # Parent family
    cards=List[Card],            # Required cards
    suit=str,                    # Spell suit
    key_cards=List[Card],        # Core cards
    number_card=Card,            # Power/duration card (optional)
    upgrade_card=Card,           # Upgrade card (optional)
    requires_target=bool,        # Needs target selection
    target_type=str,             # Type of target (optional)
)
```

### Target Types

- `'own_figure'` - Player's own figures
- `'opponent_figure'` - Opponent's figures
- `'any_figure'` - Any figure on the field
- `'player'` - Player target
- `None` - No target required

## Spell Execution Flow

1. Player selects spell family from CastSpellScreen
2. Available spell variants displayed based on cards in hand
3. Player selects specific spell variant
4. If `requires_target=True`, player selects target
5. `spell.execute(game, target)` is called
6. Spell logic executes and updates game state
7. Cards removed from hand
8. Log entry created

## Example Spell Patterns

### Simple Direct Effect
```python
# Single card, no target
spell = Spell(
    name="Draw Card",
    family=family,
    cards=[Card(suit, 'A')],
    suit=suit,
    key_cards=[Card(suit, 'A')],
    requires_target=False,
)
```

### Power-Scaling Effect
```python
# Multiple cards, power from number_card
spell = Spell(
    name=f"Heal {power} HP",
    family=family,
    cards=[key1, key2, number_card],
    suit=suit,
    key_cards=[key1, key2],
    number_card=number_card,
    requires_target=False,
)
```

### Figure Attachment
```python
# Passive spell attached to figure
spell = Spell(
    name="Shield",
    family=family,
    cards=[card1, card2],
    suit=suit,
    key_cards=[card1, card2],
    requires_target=True,
    target_type='own_figure',
)
# Set duration based on number_card:
# spell.duration = spell.get_power()
```

### Battle Modification
```python
# Changes battle type
spell = Spell(
    name="Force Siege Battle",
    family=family,
    cards=[Card(suit, 'K')],
    suit=suit,
    key_cards=[Card(suit, 'K')],
    requires_target=False,
)
```

## Next Steps

1. **Create actual spell configs** - Define your game's spells
2. **Implement spell execution logic** - Add custom `execute()` methods
3. **Create spell images** - Design and add spell icons and frames
4. **Add database support** - Store active spells in database if needed
5. **Implement target selection UI** - Add UI for selecting spell targets
6. **Add spell effects to game logic** - Integrate spell effects with game mechanics

## Notes

- Each spell family can have multiple spell instances (different card combinations)
- Spells use the same card matching system as figures
- Greyscale display automatically shows which spells can't be cast
- Spell power is typically derived from the `number_card` rank
- Upgrades can be implemented via `upgrade_card` or custom logic
