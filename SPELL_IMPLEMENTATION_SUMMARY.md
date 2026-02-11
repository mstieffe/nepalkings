# Spell Casting Implementation Summary

## What Has Been Implemented

### 1. Architecture & Planning ✅
- Created comprehensive implementation plan in `SPELL_IMPLEMENTATION_PLAN.md`
- Designed confirmation flow similar to figure building
- Designed counter spell mechanism for client-side handling
- Defined spell type effects (greed, enchantment, tactics)

### 2.Database Models ✅
- **ActiveSpell Model**: Tracks active spell effects in games
  - Stores spell name, type, family, suit, caster, target
  - Tracks pending state (for counterable spells)
  - Stores effect data as JSON for flex ibility- Includes duration and active status

- **Game Model Updates**:
  - `pending_spell_id`: References spell waiting for counter
  - `battle_modifier`: JSON field for tactics spell effects
  - `waiting_for_counter_player_id`: Which player can counter

### 3. Server-Side API ✅
Created `server/routes/spells.py` with endpoints:

- **POST /spells/cast_spell**: Cast any spell (handles both counterable and non-counterable)
- **POST /spells/counter_spell**: Counter an opponent's spell
- **POST /spells/allow_spell**: Allow opponent's spell without countering
- **GET /spells/get_active_spells**: Fetch active spell effects
- **GET /spells/get_pending_spell**: Get details of pending spell
- **POST /spells/remove_spell_effect**: Deactivate a spell effect

Features:
- Validates player turn and card availability
- Marks spell cards as used (removes from hand)
- Creates ActiveSpell records in database
- Handles pending state for counterable spells
- Logs all spell actions
- Returns updated game state

### 4. Client-Side Service ✅
Created `utils/spell_service.py`:

- `cast_spell()`: Send spell to server
- `counter_spell()`: Counter opponent's spell
- `allow_spell()`: Allow spell without countering
- `fetch_active_spells()`: Get active effects
- `fetch_pending_spell()`: Get pending spell details
- `remove_spell_effect()`: Remove spell effect
- Full error handling and timeout management

### 5. UI Integration ✅
Updated `cast_spell_screen.py`:

- **Confirmation Dialogue Flow**:
  - Click confirm → Show "Do you want to cast [SpellName]?" dialogue
  - Similar to figure building confirmation
  - Shows spell family icon
  - Indicates if spell is counterable

- **Response Handling**:
  - "Yes" → Calls spell_service.cast_spell()
  - "Cancel" → Closes dialogue
  - Shows success/error messages based on server response

- **Spell Service Integration**:
  - Maps dummy spell cards to real hand cards
  - Sends card data to server
  - Updates game state after casting
  - Clears selections after successful cast

### 6. Game State Management ✅
Updated `game/core/game.py`:

- Added spell-related properties:
  - `pending_spell_id`
  - `battle_modifier`
  - `waiting_for_counter_player_id`
  - `pending_spell`
  - `waiting_for_counter` (boolean flag)
  - `active_spell_effects`

- Updates these from server responses automatically

## What Still Needs Implementation

### Phase 1: Core Functionality
1. **Target Selection UI**:
   - When `spell.requires_target` is True
   - UI to select own figure, opponent figure, or player
   - Pass `target_figure_id` to spell_service

2. **Spell Execution Logic**:
   - Implement `_execute_spell()` in `server/routes/spells.py`
   - Each spell type needs specific logic:
     - **Greed**: Draw cards, exchange hands, discard
     - **Enchantment**: Modify figure power, destroy figures, reveal cards
     - **Tactics**: Set battle modifiers for next battle

3. **Counter Spell Notification**:
   - In `game_screen.py` or main game loop
   - Check if `game.waiting_for_counter` is True
   - Show notification dialogue: "Opponent cast [Spell]. Counter?"
   - Allow player to select counter spell or allow

### Phase 2: Battle Integration
4. **Battle Modifier Logic**:
   - Update battle system to check `game.battle_modifier`
   - Apply special rules:
     - Civil War: Both select 2 villagers of same color
     - Peasant War: Only villagers can battle
     - Blitzkrieg: Attacker selects opponent's figure
     - Invader Swap: Swap roles

5. **Enchantment Effects**:
   - Check active spell effects on figures before battle
   - Apply power modifiers (+6 boost, -6 poison)
   - Handle figure destruction (Explosion)

### Phase 3: Polish
6. **Timeout Handling**:
   - Auto-allow spell if opponent doesn't respond in time
   - Background task or server-side timeout

7. **Multiple Spells Per Turn**:
   - Currently closes screen after cast
   - Consider allowing multiple spells
   - Update turn management

8. **Visual Indicators**:
   - Show which figures have enchantments attached
   - Display active battle modifiers on field screen
   - Pending spell indicator while waiting for counter

9. **Spell Effect Duration**:
   - Track spell duration in rounds
   - Auto-remove expired effects
   - Update figure displays when effects expire

## Testing Checklist

### Basic Flow
- [ ] Can select spell family
- [ ] Can see spell variants with cards
- [ ] Can click confirm button
- [ ] Confirmation dialogue appears
- [ ] "Yes" casts spell successfully
- [ ] "Cancel" closes dialogue without casting

### Server Communication
- [ ] Spell cards are removed from hand
- [ ] Game state updates after cast
- [ ] Log entries created
- [ ] Non-counterable spells execute immediately

### Counterable Spells
- [ ] Tactics spells set pending state
- [ ] Opponent receives notification (TODO)
- [ ] Opponent can counter with own spell (TODO)
- [ ] Opponent can allow spell (TODO)
- [ ] Original spell executes after allow (TODO)

### Edge Cases
- [ ] Cannot cast on opponent's turn
- [ ] Cannot cast without required cards
- [ ] Error messages display correctly
- [ ] Network error handling
- [ ] Spell requires target but none selected (TODO)

## Next Steps (Recommended Order)

1. **Test Current Implementation**:
   - Start server with new spells blueprint
   - Test casting non-counterable spells (greed/enchantment)
   - Verify database records are created
   - Check log entries

2. **Implement First Spell**:
   - Choose simple greed spell (e.g., "Draw 2 SideCards")
   - Implement its `_execute_spell()` logic
   - Test end-to-end: cast → server executes → cards added to hand

3. **Add Counter Notification**:
   - In game_screen or field_screen update()
   - Check if `game.waiting_for_counter`
   - Show dialogue with "Counter" and "Allow" options

4. **Implement Counter Flow**:
   - Counter dialogue lets player select spell
   - Calls `spell_service.counter_spell()`
   - Allow button calls `spell_service.allow_spell()`

5. **Add Target Selection**:
   - UI to click figures when spell requires target
   - Pass selected figure ID to cast_spell()

6. **Implement Remaining Spells**:
   - Greed spells (hand manipulation)
   - Enchantment spells (figure effects)
   - Tactics spells (battle modifiers)

7. **Battle Integration**:
   - Update battle selection to check modifiers
   - Apply enchantment power modifiers
   - Implement special battle rules

8. **Polish & Testing**:
   - Add visual indicators
   - Implement timeouts
   - Comprehensive testing

## File Structure

```
nepal_kings/
├── SPELL_IMPLEMENTATION_PLAN.md      # Detailed architecture
├── nepal_kings/
│   ├── game/
│   │   ├── components/
│   │   │   └── spells/
│   │   │       ├── spell.py              # Spell & SpellFamily classes (counterable added)
│   │   │       ├── spell_icon.py         # UI components
│   │   │       ├── spell_manager.py      # Spell loading
│   │   │       └── spell_configs/        # Individual spell definitions
│   │   ├── core/
│   │   │   └── game.py                   # ✅ Updated with spell state
│   │   └── screens/
│   │       └── cast_spell_screen.py      # ✅ Updated with confirmation & service
│   └── utils/
│       └── spell_service.py              # ✅ NEW: Client-side API
│
└── server/
    ├── models.py                         # ✅ Updated with ActiveSpell model
    ├── server.py                         # ✅ Registered spells blueprint
    └── routes/
        ├── __init__.py                   # ✅ Added spells import
        └── spells.py                     # ✅ NEW: Server endpoints
```

## Configuration

No configuration changes needed. The system uses existing settings for:
- Server URL (`settings.SERVER_URL`)
- Screen positions (spell icon positions already configured)
- Database connection (existing SQLAlchemy setup)

## Notes

- **Database Migration**: When you first run the server, it will create the `active_spells` table automatically
- **Cards Removal**: Currently marks cards as `in_deck=True` to remove from hand - consider adding `part_of_spell` field
- **Spell Effect Storage**: `effect_data` JSON field allows flexibility for spell-specific parameters
- **Error Handling**: All API calls have try-catch with proper error messages
- **Turn Validation**: Server validates it's the player's turn before allowing spell cast
- **Logging**: All spell actions create log entries visible in game log

## Example Usage

```python
# In cast_spell_screen.py (already implemented):
result = spell_service.cast_spell(
    player_id=self.game.player_id,
    game_id=self.game.game_id,
    spell_name="Draw 2 SideCards",
    spell_type="greed",
    spell_family_name="Draw 2 SideCards",
    suit="Hearts",
    cards=[{"id": 1, "rank": "2", "suit": "Hearts", "value": 2}],
    target_figure_id=None,
    counterable=False
)

if result['success']:
    # Spell cast successfully
    # Game state will update automatically
```

## Questions to Address

1. **Multiple Spells**: Should players be able to cast multiple spells per turn?
2. **Spell Limit**: Any limit on spells per game/round?
3. **Counter Timeout**: How long should opponent have to counter? (suggest 60 seconds)
4. **Target Selection**: Which screen should handle target selection for spells?
5. **Spell Animation**: Any visual effects when spells are cast?
6. **Spell Cards**: Should there be a "spell graveyard" to track used spells?
