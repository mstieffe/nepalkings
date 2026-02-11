# Spell Casting Implementation Plan

## Overview
This document outlines the architecture for implementing spell casting in the Nepal Kings game, including confirmation flow, counterable spells, and server-client interaction.

## Spell Types and Their Effects

### 1. Greed Spells (Hand/Deck Manipulation)
- **Execution Timing**: Immediate
- **Counterable**: No
- **Effects**: 
  - Draw cards
  - Exchange cards with opponent
  - Discard cards
- **State Changes**: 
  - Update player hands (main_cards, side_cards)
  - Update deck positions
- **Examples**: Draw 2 SideCards, Forced Deal, Dump Cards

### 2. Enchantment Spells (Figure Effects)
- **Execution Timing**: Immediate or on next battle
- **Counterable**: No
- **Effects**:
  - Poison figure (-6 power)
  - Boost figure (+6 power)
  - Destroy figure (Explosion)
  - Enable unlimited building (Infinite Hammer)
  - Reveal opponent cards (All Seeing Eye)
- **State Changes**:
  - Create active spell effect records
  - Attach effects to figures
  - Set temporary game modifiers
- **Examples**: Poison, Health Boost, Explosion, All Seeing Eye

### 3. Tactics Spells (Battle Modifiers)
- **Execution Timing**: Set for next battle
- **Counterable**: Yes
- **Effects**:
  - Change battle rules (Civil War, Peasant War)
  - Swap invader/defender (Invader Swap)
  - Select opponent's battle figure (Blitzkrieg)
- **State Changes**:
  - Set battle_modifier field in game state
  - Create pending spell that opponent can counter
- **Examples**: Civil War, Peasant War, Blitzkrieg, Invader Swap

## Client-Side Spell Casting Flow

### Phase 1: Spell Selection (Already Implemented)
```
User → Cast Spell Screen → Select Family → Select Variant → (Select Target if needed)
```

### Phase 2: Confirmation Flow (To Implement)
```python
# Similar to figure building:
1. User clicks confirm button
2. Show dialogue box: "Do you want to cast [SpellName]?"
   - Show spell icon
   - Actions: ['yes', 'cancel']
3. If 'yes':
   - If spell.counterable:
     - Call spell_service.cast_counterable_spell()
     - Set game state to WAITING_FOR_COUNTER
     - Show status: "Waiting for opponent to counter..."
   - Else:
     - Call spell_service.cast_spell()
     - Execute spell immediately
4. Update game state
5. Close cast spell screen (or stay for multiple casts)
```

### Phase 3: Counter Flow (For Counterable Spells)
```python
# Opponent's client receives notification:
1. Notification: "Opponent cast [SpellName]. Do you want to counter?"
   - Show spell icon
   - Options: "Counter" (if has spell cards) or "Allow"
2. If "Counter":
   - Open counter spell selection dialogue
   - Select counter spell from hand
   - Confirm counter
   - Send counter to server
3. If "Allow" or timeout:
   - Server executes original spell
4. Original player receives result notification
```

### Phase 4: Spell Execution
```python
# Server executes spell and returns result:
1. Validate spell is still castable
2. Remove cards from hand
3. Execute spell effect based on type:
   - Greed: Modify hands/decks immediately
   - Enchantment: Create active effect record
   - Tactics: Set battle_modifier for next battle
4. Create log entry
5. Return updated game state to both players
```

## Server-Side Architecture

### Database Schema (New Tables/Fields)

#### active_spells table
```sql
CREATE TABLE active_spells (
    id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    spell_name TEXT NOT NULL,
    spell_type TEXT NOT NULL,  -- 'greed', 'enchantment', 'tactics'
    target_figure_id INTEGER,  -- NULL for non-targeted spells
    cast_round INTEGER NOT NULL,
    duration INTEGER DEFAULT 0,  -- 0 for instant, >0 for ongoing
    is_active BOOLEAN DEFAULT TRUE,
    effect_data TEXT,  -- JSON for spell-specific data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(id),
    FOREIGN KEY (player_id) REFERENCES players(id),
    FOREIGN KEY (target_figure_id) REFERENCES figures(id)
);
```

#### games table updates
```sql
ALTER TABLE games ADD COLUMN pending_spell_id INTEGER;
ALTER TABLE games ADD COLUMN battle_modifier TEXT;  -- JSON for battle modifications
ALTER TABLE games ADD COLUMN waiting_for_counter_player_id INTEGER;

-- pending_spell_id: Points to active_spells.id for counterable spells
-- battle_modifier: Stores active battle modifications
-- waiting_for_counter_player_id: Which player needs to respond to counter
```

### API Endpoints (To Create)

#### POST /spells/cast_spell
```python
"""
Cast a non-counterable spell (greed/enchantment types).
Immediately executes the spell effect.

Request:
{
    "player_id": int,
    "game_id": int,
    "spell_name": str,
    "spell_type": str,  # 'greed', 'enchantment', 'tactics'
    "spell_family_name": str,
    "suit": str,
    "cards": [{"rank": str, "suit": str, "id": int, ...}],
    "target_figure_id": int | None,
    "counterable": bool
}

Response:
{
    "success": bool,
    "message": str,
    "game": {...},  # Updated game state
    "spell_effect": {...}  # Details of what happened
}
```

#### POST /spells/cast_counterable_spell
```python
"""
Cast a counterable spell (tactics type).
Sets pending state for opponent to counter.

Request: Same as cast_spell

Response:
{
    "success": bool,
    "message": str,
    "game": {...},
    "spell_id": int,  # ID of pending spell
    "waiting_for_player_id": int  # Opponent's player_id
}
```

#### POST /spells/counter_spell
```python
"""
Counter a pending spell with another spell.

Request:
{
    "player_id": int,
    "game_id": int,
    "pending_spell_id": int,
    "counter_spell_name": str,
    "counter_cards": [...]
}

Response:
{
    "success": bool,
    "message": str,
    "game": {...},
    "original_spell_cancelled": bool
}
```

#### POST /spells/allow_spell
```python
"""
Allow opponent's spell to execute without countering.

Request:
{
    "player_id": int,
    "game_id": int,
    "pending_spell_id": int
}

Response:
{
    "success": bool,
    "message": str,
    "game": {...},
    "spell_effect": {...}
}
```

#### GET /spells/get_active_spells
```python
"""
Get all active spell effects for a game.

Request:
{
    "game_id": int,
    "player_id": int (optional, filter by player)
}

Response:
{
    "active_spells": [...]
}
```

#### POST /spells/remove_spell_effect
```python
"""
Remove/deactivate a spell effect (when duration expires or figure is destroyed).

Request:
{
    "spell_id": int
}

Response:
{
    "success": bool
}
```

## Client-Side Service (To Create)

### utils/spell_service.py
```python
"""
Client-side spell service for server communication.
Similar to figure_service.py pattern.
"""

def cast_spell(player_id, game_id, spell_data):
    \"\"\"Cast a non-counterable spell.\"\"\"
    
def cast_counterable_spell(player_id, game_id, spell_data):
    \"\"\"Cast a counterable spell (sets pending state).\"\"\"
    
def counter_spell(player_id, game_id, pending_spell_id, counter_data):
    \"\"\"Counter an opponent's spell.\"\"\"
    
def allow_spell(player_id, game_id, pending_spell_id):
    \"\"\"Allow opponent's spell without countering.\"\"\"
    
def fetch_active_spells(game_id, player_id=None):
    \"\"\"Fetch active spell effects.\"\"\"
```

## Game State Management

### New State Properties (game.py)
```python
class Game:
    def __init__(self, ...):
        # ... existing init ...
        self.pending_spell = None  # Spell waiting for counter
        self.waiting_for_counter = False
        self.active_spell_effects = []  # List of active enchantments
        self.battle_modifier = None  # Active battle modification
```

### State Updates
```python
def update(self):
    # ... existing update code ...
    
    # Check for pending spells requiring counter
    if game_dict.get('pending_spell_id'):
        self.pending_spell = fetch_pending_spell(game_dict['pending_spell_id'])
        self.waiting_for_counter = (
            game_dict.get('waiting_for_counter_player_id') == self.player_id
        )
    
    # Load active spell effects
    self.active_spell_effects = fetch_active_spells(self.game_id)
    self.battle_modifier = game_dict.get('battle_modifier')
```

## UI Updates

### cast_spell_screen.py Updates
```python
def handle_events(self, events):
    # ... existing event handling ...
    
    # Handle confirm button click
    if confirm_button_clicked:
        selected_spell = self.scroll_text_list_shifter.get_current_selected()
        
        # Show confirmation dialogue
        self.make_dialogue_box(
            message=f"Do you want to cast {selected_spell.name}?",
            actions=['yes', 'cancel'],
            images=[spell_family_icon],
            icon="question",
            title="Cast Spell"
        )
```

### New: counter_spell_dialogue.py (Optional)
- Special dialogue for counter spell flow
- Shows pending spell info
- Allows selection of counter spell
- Confirms/cancels counter action

### game_screen.py Updates
```python
def update(self):
    # ... existing update ...
    
    # Check if opponent cast counterable spell
    if self.game.waiting_for_counter and self.game.pending_spell:
        # Show notification
        self.show_counter_dialogue()
```

## Implementation Steps

### Step 1: Server Setup
1. Create `server/routes/spells.py`
2. Create database migration for active_spells table
3. Update games table schema
4. Implement spell casting endpoints
5. Implement counter spell endpoints

### Step 2: Client Service
1. Create `utils/spell_service.py`
2. Implement all spell service functions
3. Add error handling and validation

### Step 3: Screen Updates
1. Update `cast_spell_screen.py` with confirmation dialogue
2. Implement spell casting logic in `cast_spell_in_db()`
3. Add target selection UI for targeted spells

### Step 4: Counter Flow
1. Create counter spell notification UI
2. Implement counter spell selection
3. Add waiting state indicator

### Step 5: Spell Execution Logic
1. Implement each spell's execute() method in spell.py
2. Handle greed spell effects (draw cards, etc.)
3. Handle enchantment spell effects
4. Handle tactics spell effects

### Step 6: Battle Integration
1. Update battle logic to check battle_modifier
2. Apply enchantment effects to figure power
3. Handle special battle rules from tactics spells

### Step 7: Testing
1. Test each spell type independently
2. Test counter flow
3. Test state synchronization
4. Test edge cases (disconnection, timeout, etc.)

## Next Immediate Actions

1. **Create spell_service.py** - Client-side API wrapper
2. **Create server/routes/spells.py** - Server endpoints
3. **Update cast_spell_screen.py** - Add confirmation dialogue
4. **Update game.py** - Add spell state properties

## Notes

- **Turn Management**: Spells can only be cast on player's turn
- **Card Removal**: Spell cards are removed from hand immediately upon cast
- **Timing**: Greed spells execute immediately, enchantments attach to figures or game state, tactics wait for battle
- **Counter Window**: Need to define timeout for counter (e.g., 60 seconds)
- **Logging**: All spell casts should create log entries
- **Multiple Spells**: Consider if player can cast multiple spells per turn

## Future Enhancements

- Spell history/graveyard
- Spell effect animations
- Sound effects for spell casting
- Spell combo detection
- Counter-counter mechanism (chain countering)
- Spell cooldowns or limits per game
