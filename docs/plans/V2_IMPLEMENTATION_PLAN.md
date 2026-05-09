# Nepal Kings 2.0 — Full Implementation Plan

## Guiding Principles

1. **Code reuse**: Abstract existing screens/managers behind interfaces; don't duplicate logic.
2. **No regressions**: Existing duel functionality must remain fully intact.
3. **Test coverage**: Server-side tests for every new endpoint/model; client-side tests for state transitions and data transforms.

---

## Phase 0 — Branch Setup & Preparation

### 0.1 Create Branch
- Create branch `v2.0` from `main`

### 0.2 Server Config Scaffold
Add all new configurable constants to `server/server_settings.py`:
```python
# ── Collection & Boosters ──
STARTER_BOOSTER_PACKS = 10
BOOSTER_PACK_PRICE = 100
BOOSTER_PACK_CARDS = 3
DUEL_WINNER_BOOSTER_PACKS = 2
DUEL_LOSER_BOOSTER_PACKS = 1

BOOSTER_TIER_PROBABILITIES = {
    1: 0.60,   # common:   7, 8, 9, 10
    2: 0.30,   # uncommon: J, Q
    3: 0.10,   # rare:     K, A
}
BOOSTER_TIER_RANKS = {
    1: ['7', '8', '9', '10'],
    2: ['J', 'Q'],
    3: ['K', 'A'],
}

CARD_SELL_PRICE_NUMBER = 'value'   # sell for card value (7→7, 8→8, …)
CARD_SELL_PRICE_KEY_MULTIPLIER = 10  # J→10, Q→20, K→40, A→30
KEY_CARD_RANKS = ['J', 'Q', 'K', 'A']

# ── Kingdom ──
KINGDOM_MAP_COLS = 13
KINGDOM_MAP_ROWS = 7   # ≈91 hexes
LAND_TIER_PROBABILITIES = {1: 0.55, 2: 0.30, 3: 0.15}
LAND_GOLD_RATE_RANGES = {  # gold per hour (min, max) per tier
    1: (1, 3),
    2: (3, 7),
    3: (7, 15),
}
LAND_SUIT_BONUS_RANGES = {  # suit combat bonus value (min, max) per tier
    1: (1, 3),
    2: (3, 6),
    3: (5, 10),
}
CONQUER_COOLDOWN_SECONDS = 6 * 3600  # 6 hours

# ── AI Defence Templates ──
AI_DEFENCE_TEMPLATES = {
    1: [...],  # tier 1 templates (defined in Phase 17)
    2: [...],
    3: [...],
}
```
**Tests**: `test_server_settings.py` — validate all constants are set and within valid ranges.

---

## Phase 1 — Database Schema Extensions

### 1.1 New Models in `server/models.py`

#### `CollectionCard`
Stores a user's card collection (many rows per user, one per card copy).
```python
class CollectionCard(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    suit          = db.Column(db.String(10), nullable=False)   # hearts/diamonds/clubs/spades
    rank          = db.Column(db.String(5),  nullable=False)   # '7'..'A'
    value         = db.Column(db.Integer,    nullable=False)
    locked        = db.Column(db.Boolean,    default=False)    # True when used in conquer/defence config
    lock_type     = db.Column(db.String(20), nullable=True)    # 'conquer_figure'|'conquer_move'|'conquer_modifier'|'defence_figure'|'defence_move'|'defence_modifier'|'defence_spell'
    lock_ref_id   = db.Column(db.Integer,    nullable=True)    # FK to the config element using this card
```
- **Relationship**: `User.collection_cards` (backref)
- **Index**: `(user_id, suit, rank)` for fast lookup

#### `Land`
```python
class Land(db.Model):
    id                = db.Column(db.Integer, primary_key=True)
    col               = db.Column(db.Integer, nullable=False)
    row               = db.Column(db.Integer, nullable=False)
    tier              = db.Column(db.Integer, nullable=False)   # 1-3
    gold_rate          = db.Column(db.Float,   nullable=False)   # gold per hour
    suit_bonus_suit    = db.Column(db.String(10), nullable=False)
    suit_bonus_value   = db.Column(db.Integer, nullable=False)
    owner_user_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    owned_since        = db.Column(db.DateTime, nullable=True)
    defence_config_id  = db.Column(db.Integer, db.ForeignKey('land_config.id'), nullable=True)
    ai_template_index  = db.Column(db.Integer, nullable=True)  # index into AI_DEFENCE_TEMPLATES[tier]
```
- **Unique constraint**: `(col, row)`
- **Index**: `owner_user_id`

#### `LandConfig`
Shared schema for both conquer and defence configurations.
```python
class LandConfig(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    config_type    = db.Column(db.String(10), nullable=False)  # 'conquer' | 'defence'
    land_id        = db.Column(db.Integer, db.ForeignKey('land.id'), nullable=True)  # defence: which land; conquer: NULL
    # Battle modifier
    battle_modifier = db.Column(db.JSON, nullable=True)  # {'type': 'Blitzkrieg'|'Peasant War'|'Civil War'}
    # Battle figure(s) — defence only
    battle_figure_id   = db.Column(db.Integer, db.ForeignKey('land_config_figure.id'), nullable=True)
    battle_figure_id_2 = db.Column(db.Integer, db.ForeignKey('land_config_figure.id'), nullable=True)  # civil war
    # Spell — defence only (alternative to battle figure)
    spell_name      = db.Column(db.String(50), nullable=True)   # 'health_boost' | 'poison'
    spell_target_figure_id = db.Column(db.Integer, nullable=True)  # health boost target
    spell_card_ids  = db.Column(db.JSON, nullable=True)  # collection card IDs used for spell
    # Auto-gambling — defence only
    auto_gamble     = db.Column(db.Boolean, default=False)
    created_at      = db.Column(db.DateTime, default=db.func.now())
```
- **Constraint**: Per user, at most 1 conquer config (`config_type='conquer'`).
- **Relationships**: `figures` (LandConfigFigure), `battle_moves` (LandConfigBattleMove)

#### `LandConfigFigure`
Figures built in a conquer/defence configuration.
Mirrors all gameplay-relevant fields from the duel `Figure` model so that conquer/defence
figures behave identically (skills, info box, upgrades, etc.).
```python
class LandConfigFigure(db.Model):
    id                  = db.Column(db.Integer, primary_key=True)
    config_id           = db.Column(db.Integer, db.ForeignKey('land_config.id'), nullable=False)
    family_name         = db.Column(db.String(50), nullable=False)
    name                = db.Column(db.String(50), nullable=False)
    suit                = db.Column(db.String(10), nullable=False)
    color               = db.Column(db.String(10), nullable=False)  # 'offensive'|'defensive'
    field               = db.Column(db.String(10), nullable=False)  # 'castle'|'village'|'military'
    card_ids            = db.Column(db.JSON, nullable=False)         # [collection_card.id, ...]
    card_roles          = db.Column(db.JSON, nullable=False)         # ['key','key','number'] etc.
    produces            = db.Column(db.JSON, nullable=True)          # Resources produced
    requires            = db.Column(db.JSON, nullable=True)          # Resources required
    description         = db.Column(db.String(255), nullable=True)
    upgrade_family_name = db.Column(db.String(50), nullable=True)
    checkmate           = db.Column(db.Boolean, default=False)       # Maharaja: loss on death
    cannot_be_blocked   = db.Column(db.Boolean, default=False)       # Prevents counter-advance
    rest_after_attack   = db.Column(db.Boolean, default=False)       # Rests 1 round after battle
```
**Skills not stored as columns** (`cannot_attack`, `must_be_attacked`, `distance_attack`,
`buffs_allies`, `buffs_allies_defence`, `blocks_bonus`, `cannot_defend`, `instant_charge`,
`cannot_be_targeted`) are derived from `family_name` via `FAMILY_SKILLS` lookup — same as duel
`Figure` model.

**Resource deficit**: conquer/defence figures obey the same deficit rules as duel figures.
`kingdom_service.check_land_config_deficit(figure, all_config_figures)` uses the same iterative
algorithm as `_check_figure_resource_deficit` in `routes/games.py`. A figure in deficit **cannot
be selected as battle figure** and is shown greyed-out with the broken-state icon on the
conquer/defence field screen.

**Figure detail info box**: Clicking a figure on the conquer/defence field opens the same
`FigureDetailBox` used in duel mode — showing cards, power, skills, production/requirements,
deficit status. Upgrade button shown when `upgrade_family_name` is set. On the conquer/defence
screens the action buttons adapt: no "Advance" (handled separately), but "Remove Figure"
(unlocks collection cards) and "Upgrade" (if applicable) are available.
```

#### `LandConfigBattleMove`
Battle moves purchased in a conquer/defence configuration.
```python
class LandConfigBattleMove(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    config_id       = db.Column(db.Integer, db.ForeignKey('land_config.id'), nullable=False)
    family_name     = db.Column(db.String(50), nullable=False)
    card_id         = db.Column(db.Integer, nullable=False)      # collection_card.id
    suit            = db.Column(db.String(10), nullable=False)
    rank            = db.Column(db.String(5),  nullable=False)
    value           = db.Column(db.Integer, nullable=False)
    round_index     = db.Column(db.Integer, nullable=False)      # 0, 1, 2
    call_figure_id  = db.Column(db.Integer, db.ForeignKey('land_config_figure.id'), nullable=True)
```

#### `LandAttackLog`
History of land battles.
```python
class LandAttackLog(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    land_id         = db.Column(db.Integer, db.ForeignKey('land.id'), nullable=False)
    attacker_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    defender_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # NULL for AI
    result          = db.Column(db.String(10), nullable=False)    # 'attacker_won' | 'defender_won'
    card_won_suit   = db.Column(db.String(10), nullable=True)
    card_won_rank   = db.Column(db.String(5),  nullable=True)
    card_lost_suit  = db.Column(db.String(10), nullable=True)
    card_lost_rank  = db.Column(db.String(5),  nullable=True)
    seen_by_defender = db.Column(db.Boolean, default=False)
    timestamp       = db.Column(db.DateTime, default=db.func.now())
```

### 1.2 User Model Extensions
Add to existing `User` model:
```python
booster_packs       = db.Column(db.Integer, default=0)
last_gold_collection = db.Column(db.DateTime, nullable=True)  # for on-demand gold production
last_conquer_at     = db.Column(db.DateTime, nullable=True)    # cooldown tracking
```

### 1.3 Map Seeding
Add `seed_kingdom_map()` function in `server/kingdom_service.py`:
- Called on DB reset / server init (if `Land` table is empty)
- Generates `KINGDOM_MAP_COLS × KINGDOM_MAP_ROWS` lands
- Assigns tier via weighted random using `LAND_TIER_PROBABILITIES`
- Assigns gold_rate from `LAND_GOLD_RATE_RANGES[tier]`
- Assigns suit_bonus (random suit, value from `LAND_SUIT_BONUS_RANGES[tier]`)
- Assigns AI template index for unowned lands

### 1.4 Registration Hook
Modify `register` endpoint in `server/routes/auth.py`:
- After creating User, grant `STARTER_BOOSTER_PACKS` booster packs

**Tests**:
- `tests/server/test_models_v2.py`: CRUD for all new models
- `tests/server/test_map_seeding.py`: Correct land count, tier distribution, gold rates
- `tests/server/test_registration_starter.py`: New user gets starter booster packs

---

## Phase 2 — Collection Server Endpoints

### 2.1 New Blueprint: `server/routes/collection.py`

#### `GET /collection/cards`
Returns user's card collection grouped by (suit, rank) with counts and lock status.
```json
{
  "cards": [
    {"suit": "hearts", "rank": "K", "value": 4, "total": 3, "locked": 1, "free": 2}
  ],
  "booster_packs": 2,
  "gold": 150
}
```

#### `POST /collection/sell_card`
Params: `{suit, rank, quantity}`
- Validate user has enough free (unlocked) copies
- Calculate price: number cards → card value × quantity; key cards (J/Q/K/A) → card value × 10 × quantity
- Delete `quantity` unlocked CollectionCard rows
- Add gold to User
- Return updated gold + collection
- **Test**: sell more than owned → error; sell locked → error; correct gold calculation

#### `POST /collection/buy_booster`
Params: `{quantity}`
- Validate user has `quantity × BOOSTER_PACK_PRICE` gold
- Deduct gold, add booster_packs
- Return updated state
- **Test**: insufficient gold → error; correct deduction

#### `POST /collection/open_booster`
No params (opens 1 pack).
- Validate `user.booster_packs >= 1`
- Decrement booster_packs
- Draw `BOOSTER_PACK_CARDS` random cards:
  1. Roll tier using `BOOSTER_TIER_PROBABILITIES`
  2. Pick random rank from `BOOSTER_TIER_RANKS[tier]`
  3. Pick random suit (uniform)
  4. Look up value from `RANK_TO_VALUE`
  5. Create `CollectionCard` row
- Return drawn cards: `[{suit, rank, value}, ...]`
- **Test**: no packs → error; correct tier distribution (statistical); cards added to DB

**Tests**: `tests/server/test_collection.py` — all endpoints with edge cases.

---

## Phase 3 — Gold Production Endpoint

### 3.1 Server-Side Gold Calculation
Add to `server/routes/collection.py` (or `server/routes/kingdom.py`):

#### `POST /kingdom/collect_gold`
Called periodically by client (or on kingdom screen load).
- Fetch all `Land` records where `owner_user_id = current_user.id`
- Calculate total gold_rate (sum of all owned lands' gold_rate)
- Elapsed = `now - user.last_gold_collection` (capped at reasonable max, e.g. 7 days)
- Earned = `floor(total_gold_rate × elapsed_hours)`
- Credit earned to `user.gold`, update `last_gold_collection = now`
- Return: `{gold_earned, total_gold, total_production_rate}`
- **Security**: Timestamp is server-authoritative. Client cannot manipulate.
- **Test**: Time mocking to verify correct calculation; cap max accumulation

---

## Phase 4 — Menu Restructure (Client)

### 4.1 Modify `GameMenuScreen`
Currently has 3 buttons: New Game, Load Game, Rankings.
Change to 4 buttons: **Duel**, **Kingdom**, **Collection**, **Rankings**.

- `Duel` → `self.state.screen = 'duel_menu'`
- `Kingdom` → `self.state.screen = 'kingdom'`
- `Collection` → `self.state.screen = 'collection'`
- `Rankings` → `self.state.screen = 'ranking'` (unchanged)

Update button labels, positions (4 buttons vertically stacked instead of 3), and title.

### 4.2 Add `State.screen` values
Add to screen routing in `nepal_kings/nepal_kings.py` (or wherever screen dispatch lives):
- `'duel_menu'` → `DuelMenuScreen`
- `'kingdom'` → `KingdomScreen`
- `'collection'` → `CollectionScreen`

### 4.3 Update `game_menu_settings.py`
Adjust button positions for 4 entries. Add booster pack display position (below gold).

### 4.4 Booster Pack Display
Add booster pack count display below gold in `MenuScreenMixin._draw_menu_chrome()`:
- Icon: `booster_pack.png` (already exists)
- Value: `self.state.user_dict.get('booster_packs', 0)`
- Same style as gold display

**Tests**: `tests/client/test_menu_navigation.py` — verify screen transitions for all 4 buttons.

---

## Phase 5 — Duel Menu Screen (Client)

### 5.1 New Screen: `nepal_kings/game/screens/duel_menu_screen.py`
Inherits `MenuScreenMixin, Screen`.

**Buttons:**
- `New Game` → `self.state.screen = 'new_game'` (existing)
- `Load Game` → `self.state.screen = 'load_game'` (existing)
- `Back` → `self.state.screen = 'game_menu'`

Layout: Same centered box as game menu with 3 buttons.
Reuse existing `NewGameScreen` and `LoadGameScreen` fully — they remain unchanged.
Just add `Back` button that returns to main menu instead of needing the home icon.

**Tests**: `tests/client/test_duel_menu.py` — verify navigation back/forward.

---

## Phase 6 — Collection Screen (Client)

### 6.1 New Screen: `nepal_kings/game/screens/collection_screen.py`
Inherits `MenuScreenMixin, Screen`.

**Layout:**
- Title: "Collection"
- Toggle buttons: **Main Cards** | **Side Cards** (highlighted when active)
- Card grid: One row per suit (Hearts, Diamonds, Clubs, Spades)
  - Within each row: key cards first (A, K, Q, J) then number cards (10, 9, 8, 7) — or (6, 5, 4, 3, 2) for side cards
  - Each card rendered as a `CardImg` (existing component)
  - Greyed out if user owns 0 copies
  - Badge overlay showing count if > 0 (e.g. "×3")
- Bottom buttons: **Open Booster** | **Buy Booster**
  - Greyed out when not available (0 packs / insufficient gold)
  - Clicking greyed button → notification dialogue explaining why
- **Back** button → `self.state.screen = 'game_menu'`

### 6.2 Card Click → Sell Dialogue
On clicking a card the user owns:
- `DialogueBox` with card image, "Sell this card?"
- Quantity selector: integer from 1 to owned-free count
  - Render as `< N >` with left/right arrows
- Price display: `N × price = total gold`
- Buttons: **Sell** | **Cancel**
- On confirm: POST `/collection/sell_card`

### 6.3 Buy Booster Dialogue
- `DialogueBox` with booster_pack.png image
- Quantity selector: 1 to `floor(gold / BOOSTER_PACK_PRICE)`
- Total cost display
- Buttons: **Buy** | **Cancel**
- On confirm: POST `/collection/buy_booster`

### 6.4 Open Booster → Reveal Flow
**Step 1 — Confirm dialogue:**
- "Open a booster pack?" with booster image
- Buttons: **Open** | **Cancel**

**Step 2 — Reveal dialogue (new custom component):**
- Shows 3 face-down cards (card back image)
- Each card has **white glow** initially
- **Hover**: card scales up (1.2×), glow changes to **orange**
- **Click**: card flips to reveal actual card image, **yellow glow**, stays bright
- Order of reveal is user-controlled (click any of the 3)
- Once all 3 revealed → show **Close** button
- Implementation: Custom `BoosterRevealOverlay` class in `nepal_kings/game/components/booster_reveal.py`
  - Manages 3 card slots with state: `hidden` | `hovered` | `revealed`
  - Renders glow images from existing `glow/` assets
  - Card back image: use existing card back or create one

### 6.5 Client Settings
Add to `nepal_kings/config/collection_settings.py`:
- Card grid positions, sizes, spacing
- Badge font/color/offset
- Booster reveal overlay dimensions
- Sell dialogue layout

**Tests**:
- `tests/client/test_collection_screen.py`: card grouping, sorting, grey-out logic, sell price calculation
- `tests/server/test_collection.py`: all endpoints (covered in Phase 2)

---

## Phase 7 — Booster Rewards After Duel

### 7.1 Server: `_finalize_game_over()` Enhancement
In `server/routes/games.py`, add to existing `_finalize_game_over()`:
```python
winner_user.booster_packs += DUEL_WINNER_BOOSTER_PACKS
loser_user.booster_packs += DUEL_LOSER_BOOSTER_PACKS
```
Include booster pack counts in game-over response.

### 7.2 Client: Game-Over Dialogue Enhancement
In `game_screen.py` `_show_game_over_dialogue()`:
- Add line: "You received N booster packs!" with booster icon
- Already has stats section — extend with booster reward info

**Tests**: `tests/server/test_game_over_boosters.py` — verify booster award on game end.

---

## Phase 8 — Rankings Toggle

### 8.1 Server: Kingdom Rankings Endpoint
Add `GET /auth/get_kingdom_rankings` returning:
```json
[{
  "username": "player1",
  "lands_owned": 5,
  "total_gold_rate": 23.5,
  "conquer_attempts": 12,
  "conquer_wins": 8,
  "defence_wins": 3
}]
```
Query: JOIN `Land` + `LandAttackLog` aggregated per user.

### 8.2 Client: `RankingScreen` Toggle
Add toggle tabs at top: **Duel** | **Kingdom**
- Duel: existing ranking table (unchanged)
- Kingdom: new columns (Lands, Production, Conquers, C-Wins, D-Wins)
- Default tab: Duel (preserves current behavior)

**Tests**:
- `tests/server/test_kingdom_rankings.py`
- `tests/client/test_ranking_toggle.py`

---

## Phase 9 — Kingdom Screen: Hex Map

### 9.1 Server: Kingdom Data Endpoint
New blueprint: `server/routes/kingdom.py`

#### `GET /kingdom/map`
Returns all lands with ownership info:
```json
{
  "lands": [{
    "id": 1, "col": 0, "row": 0, "tier": 2,
    "gold_rate": 5.0, "suit_bonus_suit": "hearts", "suit_bonus_value": 4,
    "owner": {"user_id": 3, "username": "player1", "owned_since": "2026-04-01T..."},
    "is_mine": true
  }],
  "my_total_gold_rate": 23.5,
  "my_lands_count": 5,
  "conquer_cooldown_remaining": 3600  // seconds until next conquer allowed, 0 if ready
}
```

### 9.2 Client: `KingdomScreen`
New screen: `nepal_kings/game/screens/kingdom_screen.py`
Inherits `MenuScreenMixin, Screen`.

**Hex Map Renderer** (`nepal_kings/game/components/hex_map.py`):
- Class `HexMap`:
  - `__init__(self, lands_data, window)` — builds hex grid from server data
  - Properties: `camera_x`, `camera_y`, `zoom` (1.0 default, 0.5–3.0 range)
  - Each hex: `HexTile` with center position, tier color, icons for gold_rate & suit bonus
  - Owner coloring: different border/fill color per owner (hash-based color from user_id), empty = grey
- **Hex geometry**: Flat-top hexagons
  - Hex width = `size * 2`, hex height = `size * sqrt(3)`
  - Offset coordinates (odd-r offset for rectangular grid)
  - Pixel position: `x = col * 1.5 * size`, `y = row * sqrt(3) * size + (col%2) * sqrt(3)/2 * size`
- **Camera controls**:
  - Click+drag on empty area → pan
  - Mouse wheel → zoom (centered on cursor)
  - Navigation buttons (arrows + zoom +/−) in corner
- **Minimap** (bottom-right corner):
  - Scaled-down render of full map (~150×100px)
  - Viewport rectangle showing current visible area
  - Click on minimap → jump camera to that position
- **Hex interaction**:
  - Hover → hex brightens, slight scale
  - Click → open `LandDetailBox`

### 9.3 `LandDetailBox` Component
`nepal_kings/game/components/land_detail_box.py`

Modal overlay displaying:
- Land name: "Land (col, row)" or generated name
- Tier (with star icons: ★/★★/★★★)
- Gold production rate
- Suit bonus: suit icon + value
- Owner: username + "since [date]" (or "Unclaimed")
- If owned by player: number of defence figures, defence battle figure icon
- **Buttons**:
  - Not owned by player → **Conquer** (greyed if cooldown active, with remaining time)
  - Owned by player → **Configure Defence**
- Close: click outside or X button

**Tests**:
- `tests/server/test_kingdom_map.py`: endpoint returns correct data
- `tests/client/test_hex_map.py`: hex coordinate math, camera bounds, tile lookup from pixel

---

## Phase 10 — Card Source Abstraction (Key Refactor)

This is the critical refactoring phase that enables reuse of `BuildFigureScreen` and `BattleShopScreen` for kingdom configs.

### 10.1 `CardSource` Interface
Create `nepal_kings/game/core/card_source.py`:
```python
class CardSource:
    """Abstract interface for providing cards to build screens."""
    def get_cards(self) -> tuple[list, list]:
        """Return (main_cards, side_cards) available for use."""
        raise NotImplementedError
    
    def get_used_card_ids(self) -> set:
        """Return IDs of cards already locked/used in this context."""
        raise NotImplementedError
    
    def get_figures(self, families, is_opponent=False) -> list:
        """Return figures already built in this context."""
        raise NotImplementedError
```

### 10.2 `GameCardSource` (Wraps existing Game)
```python
class GameCardSource(CardSource):
    def __init__(self, game):
        self.game = game
    def get_cards(self):
        return self.game.get_hand()
    def get_used_card_ids(self):
        return self.game.get_used_card_ids()
    def get_figures(self, families, is_opponent=False):
        return self.game.get_figures(families, is_opponent)
```

### 10.3 `CollectionCardSource` (For conquer/defence)
```python
class CollectionCardSource(CardSource):
    def __init__(self, collection_cards, config_figures, locked_card_ids):
        self._cards = collection_cards      # full collection as Card objects
        self._figures = config_figures       # already-built LandConfigFigures
        self._locked = locked_card_ids      # already used in this config
    def get_cards(self):
        free = [c for c in self._cards if c.id not in self._locked]
        main = [c for c in free if c.rank in MAIN_RANKS]
        side = [c for c in free if c.rank in SIDE_RANKS]
        return main, side
    def get_used_card_ids(self):
        return self._locked
    def get_figures(self, families, is_opponent=False):
        return self._figures
```

### 10.4 Refactor `BuildFigureScreen`
- Replace direct `self.game.get_hand()` calls with `self.card_source.get_cards()`
- Replace `self.game.get_figures(...)` with `self.card_source.get_figures(...)`
- Add `card_source` parameter to `__init__` (default: `GameCardSource(self.state.game)` for backward compat)
- Add `on_build_callback` parameter: function called on successful build
  - Duel mode: calls existing server endpoint (unchanged)
  - Kingdom mode: calls new kingdom build endpoint
- Add `mode` parameter: `'duel'` (default) | `'conquer'` | `'defence'`
  - Controls which server endpoint to call
  - Controls whether instant-charge advance is offered (duel only)

### 10.5 Refactor `BattleShopScreen`
- Same pattern: `card_source` parameter
- `on_buy_callback` / `on_return_callback` for server call abstraction
- In kingdom mode: calls new kingdom battle move endpoints

### 10.6 Refactor `CastSpellScreen`
- Same pattern for spell purchasing in defence configs
- Limited to `health_boost` and `poison` spells in defence mode

**Tests**:
- `tests/client/test_card_source.py`: GameCardSource wraps game correctly; CollectionCardSource filters locked cards
- **Regression**: Run ALL existing tests to verify duel mode is unchanged

---

## Phase 11 — Conquer Screen (Client)

### 11.1 New Screen: `nepal_kings/game/screens/conquer_screen.py`
Inherits `SubScreen` (displayed as overlay from KingdomScreen).

**Layout — Left Half: Conquer Field**
- Reuse `FieldScreen` rendering logic (compartments: castle, village, military)
  - But only player figures (no opponent side)
  - Data source: `LandConfig` figures from server
  - **Resource deficit**: figures in deficit are greyed out with the broken-state icon, just like in duel mode. Use `kingdom_service.get_config_deficit_map(config_id)` to annotate each figure.
  - **Figure detail info box**: clicking a field figure opens `FigureDetailBox` (same component as duel mode) showing cards, power, skills, production/requirements, deficit status. Action buttons: "Remove Figure" (unlocks cards), "Upgrade" (if `upgrade_family_name` set).
  - **Skills display**: `FigureIcon` renders skill icons from `family_name` → `FAMILY_SKILLS` / `SKILL_KEYS` lookup — identical to duel rendering.
  - **Support bonus**: shown in figure icons via existing `get_battle_bonus()` logic (calculated from same-field same-suit figures in the config).
- **Build** button → opens `BuildFigureScreen` with `CollectionCardSource` and `mode='conquer'`
  - On successful build: server creates `LandConfigFigure` with all fields from recipe (`produces`, `requires`, `description`, `upgrade_family_name`, `checkmate`, `cannot_be_blocked`, `rest_after_attack`), locks cards
  - Returns to conquer screen (not staying on build screen)

**Layout — Right Half: Battle Configuration**
- **Battle Moves** section (3 slots):
  - Display currently selected moves (or empty slots)
  - **Edit** button → opens `BattleShopScreen` with `CollectionCardSource` and `mode='conquer'`
- **Battle Modifier** section:
  - Display current modifier (or "None")
  - **Edit** button → opens modifier selection dialogue
  - Only `Blitzkrieg` available for conquer
  - Selection carousel similar to spell selection (with card cost)
- **"To Battle!"** button:
  - Enabled when: ≥1 non-deficit figure on field AND 3 battle moves selected
  - Greyed out otherwise (show tooltip if all figures are in deficit)
  - On click: initiates land battle (Phase 15)

### 11.2 Server Endpoints: `server/routes/kingdom.py`

#### `POST /kingdom/conquer/build_figure`
Same logic as `/figures/create_figure` but:
- Reads from `CollectionCard` instead of `MainCard`
- Creates `LandConfigFigure` (with all recipe fields: `produces`/`requires`, `description`, `upgrade_family_name`, `checkmate`, `cannot_be_blocked`, `rest_after_attack`) instead of `Figure`
- Locks the collection cards
- Returns updated conquer config

#### `POST /kingdom/conquer/remove_figure`
Removes a figure from conquer config, unlocks its collection cards.

#### `POST /kingdom/conquer/buy_battle_move`
Same as `/battle_shop/buy_battle_move` but for conquer config.
- Locks the collection card (conquer moves get consumed after battle, but locked during config)

#### `POST /kingdom/conquer/return_battle_move`
Unlocks the card, removes the battle move from config.

#### `POST /kingdom/conquer/set_modifier`
Set battle modifier for conquer config. Validate card availability.

#### `POST /kingdom/conquer/remove_modifier`
Clear modifier, unlock cards.

#### `GET /kingdom/conquer/config`
Returns current conquer configuration. Each figure in the response includes a `has_deficit` flag
computed via `kingdom_service.get_config_deficit_map(config_id)`.

**Shared Logic**: Extract common figure-building validation into `server/kingdom_service.py` helper functions, reusing the same card-matching and figure-family validation that `server/routes/figures.py` uses. Do NOT duplicate that logic.

**Tests**: `tests/server/test_conquer_config.py` — build/remove figures, buy/return moves, card locking, **resource deficit detection**.

---

## Phase 12 — Defence Screen (Client)

### 12.1 New Screen: `nepal_kings/game/screens/defence_screen.py`
Very similar to `ConquerScreen` but with these differences:

**Left Half: Defence Field**
- Same compartment display as conquer
- Same build button (but `mode='defence'`, calls defence endpoints)
- **Resource deficit**: same as conquer — figures in deficit are greyed out with the broken-state icon.
- **Figure detail info box**: clicking a field figure opens `FigureDetailBox` — same as conquer/duel. Shows cards, power, skills, production/requirements, deficit status. Action buttons: "Remove Figure", "Upgrade".
- **Skills & support bonus**: rendered identically to conquer field (via `family_name` → skill lookup).

**Right Half: Battle Configuration**
- **Battle Moves** section — same as conquer
- **Battle Modifier** section:
  - Allowed modifiers: `Peasant War`, `Civil War` (NOT Blitzkrieg)
- **Battle Figure** section (NEW — not in conquer):
  - Displays selected battle figure's full icon (or empty)
  - **Edit** button → opens figure selection overlay:
    - Show all figures on defence field
    - Grey out figures incompatible with current battle modifier
    - **Grey out figures with resource deficit** (cannot be selected as battle figure)
    - Click to select → confirm → assign as battle figure
    - Civil War: select TWO same-color figures (neither may have deficit)
  - Constraint validation:
    - If modifier changes and invalidates current battle figure → auto-clear selection
    - If battle figure selected → spell cannot be selected (and vice versa)
- **Spell** section (alternative to battle figure):
  - Available: `Health Boost`, `Poison`
  - Selection via carousel (same as modifier selection)
  - Health Boost: must assign target field figure after purchase
  - Poison: no target needed (auto-targets attacker's battle figure)
  - Requires card from collection (locked)
  - Max 1 spell
- **Auto-Gamble** checkbox:
  - Toggle on/off, persisted to `LandConfig.auto_gamble`

### 12.2 Server Endpoints (additions to `server/routes/kingdom.py`)
Mirror conquer endpoints but for defence:
- `POST /kingdom/defence/{land_id}/build_figure`
- `POST /kingdom/defence/{land_id}/remove_figure`
- `POST /kingdom/defence/{land_id}/buy_battle_move`
- `POST /kingdom/defence/{land_id}/return_battle_move`
- `POST /kingdom/defence/{land_id}/set_modifier`
- `POST /kingdom/defence/{land_id}/set_battle_figure`
- `POST /kingdom/defence/{land_id}/set_spell`
- `POST /kingdom/defence/{land_id}/clear_battle_figure`
- `POST /kingdom/defence/{land_id}/clear_spell`
- `POST /kingdom/defence/{land_id}/set_auto_gamble`
- `GET /kingdom/defence/{land_id}/config`

All figure-returning endpoints include a `has_deficit` flag for each figure via
`kingdom_service.get_config_deficit_map(config_id)`.

### 12.3 Constraint Validation (Server-Side)
Implement in `server/kingdom_service.py`:
- `validate_battle_figure_for_modifier(figure, modifier)` → bool
  - Civil War: both figures must be same color
  - Peasant War: no restriction on figure
  - No modifier: any figure valid
- `validate_spell_no_battle_figure(config)` → bool
- `check_land_config_deficit(figure, all_config_figures)` → bool
  - Same iterative algorithm as duel deficit check
  - Called by `set_battle_figure` to reject figures in deficit
- These validators are called on every mutation endpoint

**Tests**: `tests/server/test_defence_config.py` — all endpoints, constraint validation (modifier ↔ battle figure, spell ↔ battle figure exclusion, civil war same-color, **resource deficit rejection**).

---

## Phase 13 — Land Battle: Game Engine Reuse

This is the most complex phase. The approach: create a real `Game` record in "conquer mode" with pre-loaded state.

### 13.1 Server: `POST /kingdom/conquer/start_battle`
Params: `{land_id}`

**Flow:**
1. Validate cooldown (`user.last_conquer_at + CONQUER_COOLDOWN_SECONDS < now`)
2. Load attacker's conquer config + defender's defence config (or AI template)
3. **Validate resource deficits**: reject if the attacker's selected battle figure(s) have
   a deficit (via `kingdom_service.check_land_config_deficit`). A conquer with all field
   figures in deficit is also rejected.
4. Create a new `Game` record with `mode='conquer'`:
   - `state='open'`, `stake=0`
   - Create 2 `Player` records: attacker (user) + defender (land owner or AI user)
   - `turns_left = 1` for both players
   - Pre-populate `Figure` records from conquer/defence config figures
     - **Copy ALL fields**: `family_name`, `name`, `suit`, `color`, `field`, `description`, `upgrade_family_name`, `produces`, `requires`, `checkmate`, `cannot_be_blocked`, `rest_after_attack`
     - Skills derived from `family_name` will work automatically on the client (same `SKILL_KEYS` / `FAMILY_SKILLS` lookup)
   - Pre-populate `BattleMove` records from conquer/defence config moves
   - Set `battle_modifier` from configs (merge — attacker's + defender's)
   - If defender has spell: create `ActiveSpell` for it
   - Mark `ceasefire_active = False` (no ceasefire in conquer)
4. Set `user.last_conquer_at = now`
5. Return `{game_id, game: game.serialize()}`

### 13.2 Game Model Extension
Add to `Game` model:
```python
mode          = db.Column(db.String(10), default='duel')  # 'duel' | 'conquer'
land_id       = db.Column(db.Integer, db.ForeignKey('land.id'), nullable=True)
conquer_config_id = db.Column(db.Integer, db.ForeignKey('land_config.id'), nullable=True)
defence_config_id = db.Column(db.Integer, db.ForeignKey('land_config.id'), nullable=True)
```

### 13.3 Client: Conquer Game Flow
After `start_battle` returns:
1. Load game via existing `Game` class using returned `game_id`
2. Transition to `GameScreen` in `mode='conquer'`
3. **GameScreen modifications for conquer mode** (minimal):
   - Hide "Change Cards" button (`mode != 'duel'`)
   - Hide turn counter (only 1 turn)
   - Auto-advance flow: player is invader with 1 turn → immediately prompted to select battle figure and advance
   - **Resource deficit**: figures copied into the Game still carry `produces`/`requires` — the standard deficit check applies during the battle (greyed-out icons, cannot advance/fight)
   - Skip ceasefire logic
4. **Defender auto-play** (server-side, not LLM):
   - New `server/kingdom_service.py::auto_play_defender(game)`:
     - If defender has battle figure configured → auto counter-advance with that figure
     - If defender doesn't have battle figure → attacker selects defender's figure (normal flow, respecting battle modifier constraints)
     - If defender configured spell → auto-cast on configured turn (health boost on target figure, or poison on attacker battle figure)
     - Auto fight decision (never fold)
     - Battle moves auto-played in round order (index 0 → round 1, etc.)
     - Auto-gamble: if enabled + weakest card < 10, gamble it; auto-build double daggers when possible
   - Triggered via same AI hook mechanism (`trigger_ai_if_needed`) but uses simple logic, not LLM

### 13.4 Suit Bonus Application
In battle resolution (existing code in `server/routes/games.py`):
- When `game.mode == 'conquer'`:
  - Look up `Land` suit bonus
  - Add bonus to power of figures matching the land's suit
  - Applied to: base figure power, called figure power, panel display
- Client-side: `BattleScreen` reads suit bonus from game state for display

### 13.5 Post-Battle Resolution
Extend existing `finish_battle` / `_finalize_game_over` in `server/routes/games.py`:
When `game.mode == 'conquer'`:

**If attacker wins:**
1. Transfer land ownership: `land.owner_user_id = attacker.user_id`, `land.owned_since = now`
2. Prompt attacker to pick 1 card from defender's full config (all cards)
3. After pick: add card to attacker's `CollectionCard`, remove from defender's
4. Consume attacker's battle move/modifier cards (delete from `CollectionCard`)
5. Consume losing defender battle figure's cards
6. Unlock remaining defender config cards (return to defender's collection)
7. Wipe defender's config for this land
8. Convert attacker conquer config → new defence config for the land
9. Clear attacker conquer config
10. Create `LandAttackLog` record

**If defender wins:**
1. Ownership unchanged
2. Randomly select a key card from attacker's conquer config → remove from attacker's collection, add to defender's
3. Consume losing attacker battle figure's cards
4. Consume attacker's battle move/modifier cards
5. Unlock remaining attacker conquer config cards (they persist for future attempts)
6. Unlock defender config cards (defender's stay locked — they were never consumed)
7. Create `LandAttackLog` record

### 13.6 Card Pick Screen (Reuse)
The existing post-battle loot pick (`_on_victory_dialogue` → `pick_card`) can be reused:
- For conquer mode: show all cards from opponent's config instead of drawn side cards
- Same pick-one-card UI

**Tests**:
- `tests/server/test_land_battle.py`: Full battle flow — start, auto-play, resolution, ownership transfer, card consumption/locking
- `tests/server/test_land_battle_defender_wins.py`: Defender wins flow
- `tests/server/test_suit_bonus.py`: Suit advantage applied correctly
- `tests/server/test_conquer_cooldown.py`: Cooldown enforcement

---

## Phase 14 — Attack Notifications

### 14.1 Server: Unseen Attack Endpoint
#### `GET /kingdom/attack_notifications`
Returns all `LandAttackLog` entries where:
- `defender_user_id = current_user.id` AND `seen_by_defender = False`
```json
[{
  "id": 5,
  "land_col": 3, "land_row": 2,
  "attacker_username": "player2",
  "result": "attacker_won",
  "card_lost": {"suit": "hearts", "rank": "K"},
  "card_won": null,
  "timestamp": "2026-04-17T..."
}]
```

#### `POST /kingdom/attack_notifications/mark_seen`
Params: `{notification_ids: [5, 6]}`
Mark as seen.

### 14.2 Server: Attack History
#### `GET /kingdom/attack_history`
Returns paginated `LandAttackLog` for current user (both as attacker and defender).

### 14.3 Client: Notification Flow
- On `KingdomScreen` load: fetch `/kingdom/attack_notifications`
- For each unseen notification, show `DialogueBox` sequentially:
  - "Your land (col, row) was attacked by {username}!"
  - Result: "Defence successful! You won a {card}." or "Land lost! You lost a {card}."
  - Mark as seen after dismissal

### 14.4 Client: Attack History Button
- Add **History** button on KingdomScreen
- Opens scrollable list (reuse `InfoScroll` / `LogScreen` pattern)

**Tests**: `tests/server/test_attack_notifications.py` — creation, fetching, marking seen, history.

---

## Phase 15 — AI Defence Templates for Unowned Lands

### 15.1 Template Schema
In `server/server_settings.py`, define templates as structured dicts:
```python
AI_DEFENCE_TEMPLATES = {
    1: [  # Tier 1 — weak
        {
            'figures': [
                {'family_name': 'Village', 'suit': 'hearts', 'color': 'offensive', 'field': 'village',
                 'cards': [{'rank': 'Q', 'suit': 'hearts'}, {'rank': '8', 'suit': 'hearts'}]},
            ],
            'battle_moves': [
                {'family_name': 'Strike', 'rank': '7', 'suit': 'spades', 'round_index': 0},
                {'family_name': 'Strike', 'rank': '8', 'suit': 'hearts', 'round_index': 1},
                {'family_name': 'Strike', 'rank': '7', 'suit': 'clubs', 'round_index': 2},
            ],
            'battle_figure_index': 0,
            'battle_modifier': None,
            'spell': None,
            'auto_gamble': False,
        },
        # ... more tier 1 templates
    ],
    2: [...],  # Tier 2 — medium
    3: [...],  # Tier 3 — strong
}
```

### 15.2 Template Application
When a conquer battle starts against an unowned land:
- Select template: `AI_DEFENCE_TEMPLATES[land.tier][land.ai_template_index]`
- Create defender figures/moves from template (no real user, use AI user)
- Cards for AI are virtual (not from any collection)

### 15.3 AI Template Card Rewards
When beating an AI land:
- Winner's card pick: choose from AI template's card list
- Card added to attacker's collection (created as new `CollectionCard`)
- No defender collection to modify (AI has unlimited cards)

**Tests**: `tests/server/test_ai_defence_templates.py` — template loading, battle setup, rewards.

---

## Phase 16 — Integration & Polish

### 16.1 Duel Game-Over → Booster Pack Display
Already addressed in Phase 7. Verify integration with existing game-over flow.

### 16.2 Gold Display Updates
- MenuScreenMixin now shows gold from `user_dict` — ensure all screens that modify gold (sell, buy booster, gold production) update `state.user_dict['gold']`
- Add periodic gold collection call from kingdom screen

### 16.3 Navigation Guards
- Conquer button greyed during cooldown (show remaining time)
- Defence screen only accessible for owned lands
- Back buttons on all new screens

### 16.4 Error Handling
All new server endpoints must:
- Return proper error JSON with HTTP 400/403/404
- Client must handle errors with DialogueBox notifications

---

## Phase 17 — Comprehensive Testing

### New Test Files Summary

| File | Covers |
|------|--------|
| `tests/server/test_models_v2.py` | All new DB models CRUD |
| `tests/server/test_map_seeding.py` | Land generation, tier distribution |
| `tests/server/test_registration_starter.py` | Starter booster packs |
| `tests/server/test_collection.py` | Cards, sell, buy/open booster |
| `tests/server/test_gold_production.py` | On-demand calculation, security |
| `tests/server/test_kingdom_map.py` | Map endpoint |
| `tests/server/test_kingdom_rankings.py` | Kingdom ranking query |
| `tests/server/test_conquer_config.py` | Build/remove figures, moves, modifiers |
| `tests/server/test_defence_config.py` | Defence config + constraints |
| `tests/server/test_land_battle.py` | Full conquer battle flow |
| `tests/server/test_land_battle_defender_wins.py` | Defender win path |
| `tests/server/test_suit_bonus.py` | Suit advantage in battle |
| `tests/server/test_conquer_cooldown.py` | Cooldown enforcement |
| `tests/server/test_attack_notifications.py` | Notifications + history |
| `tests/server/test_ai_defence_templates.py` | AI template setup |
| `tests/server/test_game_over_boosters.py` | Duel booster rewards |
| `tests/client/test_menu_navigation.py` | Menu transitions |
| `tests/client/test_collection_screen.py` | Card display, sorting, pricing |
| `tests/client/test_card_source.py` | CardSource abstraction |
| `tests/client/test_hex_map.py` | Hex math, camera, tile lookup |
| `tests/client/test_ranking_toggle.py` | Ranking tab switch |

### Regression
- Run full existing test suite after each phase
- Specifically verify: game flow e2e, battle shop, figures, spells, AI

---

## Implementation Order (Recommended)

| Step | Phase | Description | Dependencies |
|------|-------|-------------|--------------|
| 1 | 0 | Branch + server config | — |
| 2 | 1 | DB schema + models | 0 |
| 3 | 4 | Menu restructure | — |
| 4 | 5 | Duel menu screen | 4 |
| 5 | 2 | Collection endpoints | 1 |
| 6 | 6 | Collection screen | 2, 4 |
| 7 | 7 | Booster rewards post-duel | 2 |
| 8 | 8 | Rankings toggle | — |
| 9 | 3 | Gold production | 1 |
| 10 | 9 | Kingdom screen + hex map | 1, 4 |
| 11 | 10 | Card source abstraction | — |
| 12 | 11 | Conquer screen | 9, 10, 11 |
| 13 | 12 | Defence screen | 11, 12 |
| 14 | 13 | Land battle engine | 12, 13 |
| 15 | 14 | Attack notifications | 13, 14 |
| 16 | 15 | AI defence templates | 14 |
| 17 | 16 | Integration + polish | All |
| 18 | 17 | Comprehensive testing | All |

---

## New Files Summary

### Server
- `server/routes/collection.py` — Collection blueprint
- `server/routes/kingdom.py` — Kingdom blueprint
- `server/kingdom_service.py` — Shared kingdom logic (map seeding, config validation, auto-play, gold production)

### Client
- `nepal_kings/game/screens/duel_menu_screen.py`
- `nepal_kings/game/screens/collection_screen.py`
- `nepal_kings/game/screens/kingdom_screen.py`
- `nepal_kings/game/screens/conquer_screen.py`
- `nepal_kings/game/screens/defence_screen.py`
- `nepal_kings/game/components/hex_map.py`
- `nepal_kings/game/components/land_detail_box.py`
- `nepal_kings/game/components/booster_reveal.py`
- `nepal_kings/game/core/card_source.py`
- `nepal_kings/config/collection_settings.py`
- `nepal_kings/config/kingdom_settings.py`

### Modified Files
- `server/models.py` — New models + User extensions + Game mode field
- `server/server_settings.py` — All new config constants
- `server/routes/auth.py` — Starter booster packs on registration
- `server/routes/games.py` — Booster rewards in game-over; suit bonus in conquer battles
- `nepal_kings/game/screens/game_menu_screen.py` — 4 buttons instead of 3
- `nepal_kings/game/screens/game_screen.py` — Conquer mode adjustments (hide change cards, etc.)
- `nepal_kings/game/screens/build_figure_screen.py` — CardSource abstraction
- `nepal_kings/game/screens/battle_shop_screen.py` — CardSource abstraction
- `nepal_kings/game/screens/cast_spell_screen.py` — CardSource abstraction for defence spells
- `nepal_kings/game/screens/ranking_screen.py` — Toggle tabs
- `nepal_kings/game/screens/_menu_base.py` — Booster pack display
- `nepal_kings/config/game_menu_settings.py` — 4-button layout + booster display
- `nepal_kings/nepal_kings.py` — New screen routing

---

## Feedback Round 2 (Post v2.0-conquer-redesign 85e871a)

User-driven polish + tactics-panel UX rework. Visual fixes #1–#7 are
self-contained client tweaks; #8 is a UX rework spread across
`conquer_tactics_rail.py` and the battle move detail box.

### #1 — Support lane lists every effecting figure
- **What:** Today the support lane only shows figures that actively boost
  the lane sum. It must also list:
  - figures that contributed via a *Call* (called villager/healer/etc.),
  - figures whose skill triggered Distance, Buff, or Block.
- **Where:** `_conquer_lane_support_entries.add()` callsite — extend the
  collector to capture any battle move whose target/origin figure has a
  triggered skill. Source: `battle_round.move_log` or equivalent.
- **Acceptance:** in a duel where my Carpenter buffed a figure, Carpenter
  appears on the support lane chip even if its `numeric_value == 0`.

### #2 — Hover-reveal opponent field figure
- On hover of a support-lane chip whose target is an opponent field
  figure, force the field figure icon's `back_visible = False` (or
  equivalent flip-state) for the duration of hover.
- Restore prior visibility on un-hover.
- Implement in `_draw_conquer_lane_band` hover handler + a transient
  `forced_face_up_ids` set passed to the field figure renderer.

### #3 — Connector ends at field-figure ring
- Replace the `target_rect.center` endpoint with the intersection between
  the line and the figure's outer ring.
- Helper: `_ring_edge_point(center, radius, from_point)` — returns
  `center + (from_point - center).normalize() * radius`.

### #4 — Grey out non-involved figures
- Player + opponent field figures not referenced by *any* current battle
  move should render greyed (alpha + saturation drop).
- Recompute on every battle-move update; reuse the
  `move_log.involved_figure_ids()` set.

### #5 — Duel panel sub-frame z-order
- Currently the sub-panel frames blit *after* the math content,
  occluding numbers.
- Reorder draw calls in `duel_panel.draw()`: frames first, then content.

### #6 — Battle figure icon
- Frame is too large vs the figure sprite. Shrink frame to ~`figure_size *
  1.06` (matches normal field-figure ring).
- Make hover responsive: scale up identical to normal figure icons (uses
  shared `_hover_scale_factor`).
- Number badge must blit last (foreground). Move badge blit to the very
  end of `BattleFigureIcon.draw()`.

### #7 — Round panel glow z-order
- In `round_panel._draw_section()` the glow is currently drawn *after*
  the icon. Reorder: glow → icon → badge → label.

### #8 — Tactics panel UX rework

**Scope:** Full rework. Sub-tasks (a→d).

#### #8a Layout & feedback
- **Family headers:** group rail items by `family_name` with mini-section
  headers (Daggers / Buffs / Blocks / Calls). Sticky within the rail.
- **Add/remove animations:** on tactic added → fade+slide in (200ms);
  on removed → fade+shrink out (180ms). Track via a small per-tactic
  `anim_state` dict keyed by `move_id`.
- **Result banner:** new sticky banner at top of the tactics panel
  showing the last action's outcome ("Gambled Dagger 7 → won, +14
  value", "Combined → Double Dagger Red"). Persists until next action.

#### #8b Combine flow
- Click first dagger → matching daggers (same colour, single) start a
  pulsing glow (similar to wall-call hint pulse).
- Click second eligible dagger → combine animation (cards merge to
  centre, then resolve into Double Dagger).
- **Drag-and-drop:** also support dragging dagger A onto dagger B in the
  rail; on drop with valid pair, trigger the same combine animation.
- Disable other rail interactions during the pulse phase; press Escape
  or click empty area to cancel.

#### #8c Gamble feedback
- On Gamble click: tactic icon plays a 1.0–1.4s coin-flip / dice-roll
  animation (rotating sprite or stack of frames).
- After result lands:
  - inline diff line in result banner: "Gambled X → won/lost, value Y".
  - any *new* battle moves added to the rail by the gamble glow for
    ~1.5s (use family colour, soft outer glow ramp).
- No screen shake (descoped).

#### #8d Action tray
- Disabled buttons remain visible with a tooltip explaining why
  ("Need 2 same-colour daggers", "Pick a tactic first", etc.).
- Add a soft glow/badge on the action tied to the *strongest currently
  available battle move* (highest projected damage / lane value).
  Compute via existing receipt math — `_strongest_battle_move()`.

### Implementation order
1. Visual fixes #5, #7, #6, #3 (small, isolated draw-order tweaks).
2. #4 grey-out (depends on a `involved_figure_ids` set).
3. #1, #2 (support-lane changes + hover flip).
4. #8a → #8c → #8b → #8d.

