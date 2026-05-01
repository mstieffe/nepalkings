# Kingdom Name Badge Cosmetics — Implementation Plan

## 1. Overview

Replace the current **flag** cosmetic type with a richer **name badge** cosmetic
type. The kingdom name is currently rendered as a fixed gold-text-on-dark-pill
above each owned cluster (low zoom) and as an *owner chip* at the hex's bottom
edge (high zoom). Both will become themable surfaces driven by a new
`badge_key` on `Kingdom`.

The flag rendering (procedurally drawn pole + fabric on the lower-left of each
owned cluster and at hex center-left) is **removed entirely**. The freed
visual budget is reinvested into the badge artwork.

The name badge is also **repositioned** from above the cluster to **below the
cluster** — functioning as a nameplate plinth under the suit icon — so the
suit-cluster icon and the new badge form a single vertical composition.

> Status: **Proposed**
>
> Migration policy: development DB will be reset; no migration code needed.

---

## 2. Goals

1. Retire the flag cosmetic type (rendering, settings, server catalog,
   model field, routes, tests).
2. Introduce a new `badge` cosmetic type with **8 SKUs** across 4 rarities.
3. Procedurally render each badge variant with cached surfaces, mirroring the
   pattern used in `hex_cosmetics.py` for surfaces/borders.
4. Reposition the kingdom name badge to **below the cluster** at low zoom.
5. Apply the equipped badge style to the **per-tile owner chip** at high zoom
   so the player's identity is consistent across zoom levels.
6. Add subtle shimmer/glow for epic-tier badges (cached animated frames, low
   cost on the web client).

## 3. Non-Goals

- No new server framework changes — reuse the existing
  `KINGDOM_COSMETIC_CATALOG` / `KingdomCosmeticUnlock` / equip routes.
- No font cosmetics in v1 (keep `_label_font`); only background/frame artwork
  varies per badge SKU.
- No animation beyond the optional epic shimmer (no full motion graphics).
- No badge cosmetics for non-owned kingdoms (other players' chips keep the
  current "other" styling but with their equipped badge — read-only).

---

## 4. Badge SKU Catalog (v1)

Pricing mirrors the retired flag tiers (250 / 850 / 1100 / 1600 / 1900).

| Key | Name | Rarity | Price | Visual |
|---|---|---|---|---|
| `badge_plain` | Plain Pill | default | 0 | Current dark-brown pill, gold border, gold text. Baseline. |
| `badge_parchment_scroll` | Parchment Scroll | common | 250 | Cream parchment fill with subtle ink fibers; rolled curls at each short end; ink-brown text; thin sepia border. |
| `badge_iron_plank` | Iron Riveted Plank | common | 350 | Wood-grain (warm brown gradient + fiber lines) with dark iron edge band; 4 corner rivets (small dark circles w/ highlight). |
| `badge_stone_tablet` | Stone Tablet | rare | 850 | Cool grey stone gradient, beveled chiseled edge (light top/left, dark bottom/right); inset/recessed text (dark with light underline). |
| `badge_banner_ribbon` | Banner Ribbon | rare | 1100 | Pill with **swallowtail** triangle notches cut into each short end (inheriting the retired flag's silhouette); fabric drape (vertical light/shadow band) + accent stripe along bottom. |
| `badge_gilded_laurel` | Gilded Laurel | epic | 1600 | Polished gold gradient pill, gold-leaf laurel sprigs flanking each side, soft warm glow. Includes shimmer frames. |
| `badge_obsidian_gems` | Obsidian Gems | epic | 1750 | Glossy black plate with high-spec highlight band, two inset gem cabochons (ruby/sapphire) at each end; soft cyan/red glow. Includes shimmer frames. |
| `badge_marble_serpent` | Marble Serpent Plaque | epic | 1900 | Pale veined-marble fill, gold scrollwork ends; small carved serpent/dragon heads bracketing the text (silhouettes, not detailed sprites). Includes shimmer frames. |

All badges use the same `_label_font` so text legibility is constant; only the
background art and frame change.

---

## 5. UX & Positioning Changes

### 5.1 Low zoom (kingdom cluster view)

| Element | Before | After |
|---|---|---|
| Suit cluster icon | center | center (unchanged) |
| Kingdom name badge | **above** cluster (`offset_y = -0.18 * sz`) | **below** cluster (`offset_y = +0.55 * sz` approx — to be tuned visually) |
| Flag | lower-left of cluster | **removed** |

Rationale: Below-cluster placement reads as a nameplate plinth, removes
collision with hexes/clusters above, and gives badge artwork a stable canvas
without the flag competing for the lower-left.

A new constant `HEX_GROUP_BADGE_OFFSET_Y_BELOW` will replace the existing
`HEX_GROUP_BADGE_OFFSET_Y` (renamed for clarity), with sign flipped.

### 5.2 High zoom (per-tile view)

The per-tile **owner chip** (colored dot + name pill at the hex's bottom flat
edge) inherits the equipped badge's background art and frame. The dot stays;
the chip pill is replaced by the badge surface. The chip width is calculated
from text + dot; the badge renderer accepts a target width/height so the same
art is produced at chip scale.

### 5.3 Removed visuals

- All per-tile flags at the hex center-left.
- All cluster-level flags at the lower-left of the suit icon.
- `HEX_MAP_PER_TILE_FLAG_MIN_ZOOM` setting becomes obsolete.

---

## 6. Architecture

### 6.1 New module: `nepal_kings/game/components/badge_cosmetics.py`

Mirrors `hex_cosmetics.py`. Contains:

```python
def render_badge(
    badge_key: str,
    text: str,
    font: pygame.font.Font,
    text_color: tuple,
    *,
    target_h: int | None = None,
    shimmer_phase: float = 0.0,
) -> pygame.Surface:
    """Return a cached surface containing the full badge (background art,
    frame, text). target_h scales the artwork. shimmer_phase in [0, 1)
    drives epic-tier animation; non-epic SKUs ignore it."""
```

Internally:

- `_BADGE_RENDERERS: dict[str, Callable]` maps each `badge_key` to a private
  renderer (e.g. `_render_parchment_scroll`).
- `@functools.lru_cache(maxsize=256)` keyed on
  `(badge_key, text, font_id, target_h, int(shimmer_phase * 12))`. Shimmer
  is quantized to 12 phases per cycle so the cache stays small.
- Each renderer:
  1. Measures the text via `font.size(text)`.
  2. Computes pad + base rect (per-SKU padding constants).
  3. Builds a per-pixel-alpha `Surface`.
  4. Draws background fill (gradients via numpy or row-by-row blit), frame,
     ornaments, then the pre-rendered text.
- Helper APIs:
  - `badge_rarity(badge_key) -> str`
  - `badge_supports_shimmer(badge_key) -> bool`
  - `clear_badge_cache()` (called on resolution change / theme reload).

### 6.2 Settings (`nepal_kings/config/kingdom_settings.py`)

Add:

```python
HEX_BADGE_STYLES = {
    'badge_plain': {
        'rarity': 'default',
        'fill': (80, 55, 10, 220),
        'border': (250, 221, 0),
        'text': (255, 238, 150),
        'shape': 'pill',
        'pad_x_factor': 0.40,   # of text height
        'pad_y_factor': 0.30,
    },
    'badge_parchment_scroll': {
        'rarity': 'common',
        'fill_top': (244, 232, 198, 235),
        'fill_bot': (220, 198, 154, 235),
        'border': (122, 92, 56),
        'text': (58, 36, 18),
        'shape': 'scroll',          # adds curled ends
        'fiber_color': (180, 152, 110, 60),
        'pad_x_factor': 0.55,
        'pad_y_factor': 0.32,
    },
    'badge_iron_plank': { ... 'shape': 'plank', 'rivets': 4 ... },
    'badge_stone_tablet': { ... 'shape': 'tablet', 'bevel': True ... },
    'badge_banner_ribbon': { ... 'shape': 'swallowtail', 'accent_stripe': ... },
    'badge_gilded_laurel': {
        'rarity': 'epic',
        'shape': 'pill',
        'fill_top': (252, 222, 130, 240),
        'fill_bot': (196, 154, 60, 240),
        'border': (250, 232, 168),
        'text': (62, 36, 8),
        'laurel': True,
        'shimmer': True,
    },
    'badge_obsidian_gems': { ... 'shape': 'pill', 'gems': [...], 'shimmer': True ... },
    'badge_marble_serpent': { ... 'shape': 'plaque', 'serpents': True, 'shimmer': True ... },
}

HEX_BADGE_DEFAULT_KEY = 'badge_plain'

# Repositioning
HEX_GROUP_BADGE_OFFSET_Y = 0.55          # was -0.18; now BELOW cluster
HEX_GROUP_BADGE_GAP_PX_FACTOR = 0.06     # extra gap between suit icon and badge
```

Remove (or mark deprecated and unused):
- `HEX_FLAG_STYLES`
- `HEX_MAP_PER_TILE_FLAG_MIN_ZOOM`
- `HEX_MINE_BADGE_BG`, `HEX_MINE_BORDER`, `HEX_MINE_BADGE_CLR` (still used as
  fallback by `badge_plain`; keep as the default constants but also expose
  them via `HEX_BADGE_STYLES['badge_plain']`).

### 6.3 Server (`server/server_settings.py`)

Replace `flag_*` entries in `KINGDOM_COSMETIC_CATALOG` with `badge_*` entries:

```python
KINGDOM_COSMETIC_CATALOG = {
    # --- Badges (replaces flags) ---
    'badge_plain': {'type': 'badge', 'name': 'Plain Pill', 'rarity': 'default', 'price_gold': 0},
    'badge_parchment_scroll': {'type': 'badge', 'name': 'Parchment Scroll', 'rarity': 'common', 'price_gold': 250},
    'badge_iron_plank': {'type': 'badge', 'name': 'Iron Riveted Plank', 'rarity': 'common', 'price_gold': 350},
    'badge_stone_tablet': {'type': 'badge', 'name': 'Stone Tablet', 'rarity': 'rare', 'price_gold': 850},
    'badge_banner_ribbon': {'type': 'badge', 'name': 'Banner Ribbon', 'rarity': 'rare', 'price_gold': 1100},
    'badge_gilded_laurel': {'type': 'badge', 'name': 'Gilded Laurel', 'rarity': 'epic', 'price_gold': 1600},
    'badge_obsidian_gems': {'type': 'badge', 'name': 'Obsidian Gems', 'rarity': 'epic', 'price_gold': 1750},
    'badge_marble_serpent': {'type': 'badge', 'name': 'Marble Serpent Plaque', 'rarity': 'epic', 'price_gold': 1900},
    # ... (existing border_* and surface_* entries unchanged)
}

KINGDOM_DEFAULT_STYLE = {
    'badge_key': 'badge_plain',     # was 'flag_key': 'flag_plain'
    'border_key': 'border_simple_gold',
    'surface_key': 'surface_plain',
}
```

In `server/routes/kingdom.py`:

```python
_COSMETIC_STYLE_FIELDS = {
    'badge': 'badge_key',     # replaces 'flag': 'flag_key'
    'border': 'border_key',
    'surface': 'surface_key',
}
```

### 6.4 Server model (`server/models.py`)

`Kingdom`:

```python
- flag_key = db.Column(db.String(80), nullable=False)
+ badge_key = db.Column(db.String(80), nullable=False)
```

Update `serialize_style()` to emit `badge_key` instead of `flag_key`. Since
the dev DB is reset, no Alembic migration needed — column rename happens
in-place.

### 6.5 Client rendering (`nepal_kings/game/components/hex_map.py`)

#### Removed methods
- `_draw_owner_flag()` and `_draw_owner_flag_at()` — delete entirely.
- All call sites (per-tile pass and `_draw_kingdom_badges`) cleaned up.

#### Modified `_draw_kingdom_badges(sz)`

```python
offset_y = sz * settings.HEX_GROUP_BADGE_OFFSET_Y     # now positive (below)
gap_px  = int(sz * settings.HEX_GROUP_BADGE_GAP_PX_FACTOR)
# remove `show_group_flag` and the per-cluster flag block

for badge_data in self._kingdom_badges():
    ...
    badge_key = badge_data.get('badge_key') or settings.HEX_BADGE_DEFAULT_KEY
    shimmer_phase = (pygame.time.get_ticks() % 1200) / 1200.0
    badge_surf = badge_cosmetics.render_badge(
        badge_key,
        str(badge_data['name']),
        font,
        text_color=None,                     # renderer pulls from style dict
        target_h=int(font.get_height() * 1.6),
        shimmer_phase=shimmer_phase,
    )
    label_y = scy + offset_y + cluster_icon_sz * 0.55 + gap_px
    br = badge_surf.get_rect(center=(scx, label_y))
    # drop shadow (kept generic; renderer surfaces are rectangular bbox)
    self.window.blit(_make_shadow(badge_surf), (br.x + sx, br.y + sy))
    self.window.blit(badge_surf, br)
```

#### Modified owner chip (high zoom)

In the per-tile draw routine that currently builds the owner chip pill,
replace the `pygame.draw.rect` background with a `badge_cosmetics.render_badge`
call sized to chip height. The colored dot (`HEX_OWNER_CHIP_DOT_R_FACTOR`) is
overlaid afterward. Other players' chips use *their* `badge_key`; falls back
to `badge_plain` if missing/unknown.

### 6.6 Server kingdom service

`server/kingdom_service.py` (or wherever new kingdoms are seeded): set
`badge_key=KINGDOM_DEFAULT_STYLE['badge_key']` on creation. Remove
`flag_key=...` initializations.

`kingdom_unlocked_cosmetics` / `_kingdom_style_updates_from_payload` continue
to work via `_COSMETIC_STYLE_FIELDS`; only the keys change.

### 6.7 Cosmetic shop UI (client)

Wherever the cosmetics shop iterates types (likely in
`nepal_kings/game/screens/kingdom_*` or `kingdom_config_*`):

- Replace the **Flags** tab/section with a **Badges** tab.
- Preview tile renders a sample badge using `badge_cosmetics.render_badge`
  with the kingdom's actual name (or "Sample Kingdom" placeholder).
- Sort order: default → common → rare → epic, then by price within rarity.

(Exact file names will be verified during implementation; the existing flag
shop code path is the template.)

---

## 7. Procedural Renderer Specs

Each `_render_*` function returns a `Surface(SRCALPHA)` sized
`(text_w + 2*pad_x + extra_w, text_h + 2*pad_y)` where `extra_w` covers
ornaments (e.g. swallowtail notches, laurel sprigs).

Common helpers (kept inside `badge_cosmetics.py`):
- `_vertical_gradient(rect, top_rgba, bot_rgba)`
- `_pill_path(rect, radius)` — clip mask
- `_draw_bevel(rect, light, dark)` — top/left + bottom/right edge highlights
- `_draw_text_with_outline(surface, text_surf, pos, outline_color)`
- `_draw_serif_curl(surface, side, color)` — used by scroll & swallowtail

### 7.1 `badge_plain` (default)

Filled pill `HEX_MINE_BADGE_BG`, border `HEX_MINE_BORDER`, text
`HEX_MINE_BADGE_CLR`. Drop shadow handled by caller.

### 7.2 `badge_parchment_scroll` (common)

1. Vertical gradient cream → tan, rounded-rect mask.
2. Add 6-10 random short ink fiber lines (alpha 60).
3. At each short end: draw a **curl** — a smaller filled circle behind the
   pill (offset half its radius outward) with a darker rim, simulating a rolled
   parchment edge.
4. Text in ink brown.

### 7.3 `badge_iron_plank` (common)

1. Wood-grain background: vertical gradient warm brown → darker; overlay 4-8
   long horizontal fiber strokes (alpha 80).
2. Outer 2 px iron rim (dark steel) with 1 px inner highlight.
3. Four rivets (filled circle dark + 1 px white highlight) inset from each
   corner by 4 px.
4. Text in pale ivory.

### 7.4 `badge_stone_tablet` (rare)

1. Vertical gradient cool grey → darker grey; rounded rect.
2. Top + left 2 px highlight (light grey), bottom + right 2 px shadow
   (almost-black) → bevel.
3. Text drawn in dark grey *recessed* (1 px down/right offset light grey
   highlight, then dark text on top).
4. Tiny chip nicks (1-2 px dark spots) along edges for stone feel.

### 7.5 `badge_banner_ribbon` (rare)

1. Base rounded rect in fabric color; overlay vertical drape (column
   gradient: edges 10% darker than center) for fabric folds.
2. **Swallowtail notch**: at each short end, cut a triangular bite into the
   rect by drawing a triangle of the surface's transparent color (or use a
   per-pixel mask).
3. Bottom 2 px accent stripe in trim color.
4. 1 px frame in trim color.

### 7.6 `badge_gilded_laurel` (epic, shimmer)

1. Pill base: vertical gradient gold → dark gold.
2. Inner 1 px bright highlight band along top quarter (specular).
3. Laurel sprigs: at each short end, draw 4 small leaf shapes (filled
   ellipses with darker outline) angled outward in a half-fan; tinted gold.
4. **Shimmer**: a translucent diagonal white band (alpha 40) sweeps across
   the pill; position computed from `shimmer_phase`. 12 cached frames
   (one per phase bucket).
5. Text dark brown for contrast.

### 7.7 `badge_obsidian_gems` (epic, shimmer)

1. Glossy black gradient (top dark grey 40, bottom near-black) pill.
2. Top quarter specular highlight band (alpha 60 white).
3. Two gem cabochons inset near each short end: filled circle (ruby red or
   sapphire blue), inner highlight dot (white alpha 200), outer dark ring.
4. **Shimmer**: gentle red/blue glow under each gem pulses with
   `shimmer_phase` (alpha 0-80 sine).
5. Text pale ivory.

### 7.8 `badge_marble_serpent` (epic, shimmer)

1. Veined marble: pale ivory base + 3-5 jagged thin lines (alpha 90, dark
   grey) procedurally generated from a hash of the badge text → stable
   pattern per kingdom.
2. Gold scrollwork frame (1 px gold rect + small filled corner triangles).
3. **Serpent ends**: at each short end, draw a small dragon-head silhouette
   (filled tear-drop body + pointed snout + 1 px eye dot) in tarnished
   gold. Heads face inward toward the text.
4. **Shimmer**: serpent eyes pulse (radius 1→2 px alternating).
5. Text dark slate.

---

## 8. File Change List

### New files
- `nepal_kings/game/components/badge_cosmetics.py` — renderers + cache.
- `tests/client/test_badge_cosmetics.py` — renderer smoke tests, cache hits.

### Modified files
- `nepal_kings/config/kingdom_settings.py`
  - Add `HEX_BADGE_STYLES`, `HEX_BADGE_DEFAULT_KEY`,
    `HEX_GROUP_BADGE_GAP_PX_FACTOR`.
  - Flip sign of `HEX_GROUP_BADGE_OFFSET_Y` (or rename).
  - Remove `HEX_FLAG_STYLES`, `HEX_MAP_PER_TILE_FLAG_MIN_ZOOM`.
- `nepal_kings/game/components/hex_map.py`
  - Delete `_draw_owner_flag` and `_draw_owner_flag_at`.
  - Update `_draw_kingdom_badges` to call `badge_cosmetics.render_badge`
    and reposition below cluster.
  - Update owner-chip pass (high zoom) to render via badge cosmetics.
  - Update `_kingdom_badges()` payload to include `badge_key` from
    `kingdom_row.serialize_style()`.
  - Remove all references to `flag_key`.
- Cosmetics shop screen(s) — locate via search for `'flag'` /
  `KINGDOM_COSMETIC_CATALOG` usage in `nepal_kings/game/screens/`. Replace
  flag tab with badge tab; preview uses `render_badge`.
- `server/server_settings.py`
  - Replace flag entries with badge entries in `KINGDOM_COSMETIC_CATALOG`.
  - Update `KINGDOM_DEFAULT_STYLE`.
- `server/models.py`
  - Rename `Kingdom.flag_key` → `Kingdom.badge_key`.
  - Update `serialize_style()`.
- `server/kingdom_service.py` (and any other seeders)
  - Replace `flag_key=` with `badge_key=`.
- `server/routes/kingdom.py`
  - `_COSMETIC_STYLE_FIELDS`: replace `'flag': 'flag_key'` with
    `'badge': 'badge_key'`.
- `server/RESET_DATABASE.sh` / dev seed scripts — verify they pick up the new
  default style.

### Removed
- All `flag_*` keys from catalog and code.
- `HEX_FLAG_STYLES`, `_draw_owner_flag*`,
  `HEX_MAP_PER_TILE_FLAG_MIN_ZOOM`.

### Tests to update
- `tests/server/` — any test asserting `flag_key` or flag SKUs in
  catalog responses (rename to `badge_key`).
- `tests/client/` — owner-chip / kingdom-badge rendering tests if present.

---

## 9. Testing Plan

### Unit (server)
- `KINGDOM_COSMETIC_CATALOG` contains 8 badge entries with correct rarities
  and prices.
- New kingdom defaults to `badge_key='badge_plain'`.
- Purchase + equip route accepts `{'type': 'badge', 'key': 'badge_X'}` and
  rejects unknown keys / unowned-but-not-default.
- Equip with stale `flag_key` payload returns 400 (key removed).

### Unit (client)
- `render_badge` returns a non-empty surface for every catalog key.
- LRU cache: same params → same `id()` (cache hit).
- Shimmer-supporting SKUs produce different surfaces across phases;
  non-shimmer SKUs ignore phase changes.
- Sized correctly for both cluster (font_h × 1.6) and chip (font_h × 1.0)
  scales.

### Integration
- Equip each badge SKU on a test kingdom; map renders without exceptions.
- Owner chip at high zoom uses badge style; matches cluster badge in style.
- Removed flag rendering: search confirms zero references to `flag_key`,
  `HEX_FLAG_STYLES`, `_draw_owner_flag` after change.

### Visual QA checklist (manual)
- Kingdom name reads cleanly at min and max low-zoom levels for every SKU.
- Below-cluster placement does not collide with neighboring kingdoms in
  dense map regions.
- Epic shimmer animations are subtle (no flicker / no banding) on the web
  client (pygbag build).
- Owner chip retains its colored-dot indicator; dot does not overlap
  badge ornaments (laurel sprigs, gem cabochons).

### Performance
- Frame time at low zoom on the web client: target ≤ +1 ms vs. baseline
  (cache should make repeat draws near-free).
- Cache memory ceiling: ≤ ~256 surfaces × ~6 KB ≈ 1.5 MB.

---

## 10. Implementation Phases

1. **Server schema + catalog** — rename `flag_key` → `badge_key`, swap
   catalog entries, update default style, fix routes/services. Reset dev DB.
2. **Client settings** — add `HEX_BADGE_STYLES`, flip offset, remove flag
   constants.
3. **`badge_cosmetics.py`** — implement `badge_plain` + `badge_parchment_scroll`
   first (proves the rendering + cache pipeline end-to-end).
4. **`hex_map.py` integration** — replace `_draw_kingdom_badges` body and
   delete flag draw methods. Verify low-zoom rendering with the two SKUs.
5. **Owner chip integration** (high zoom) — wire badge into chip rendering.
6. **Remaining renderers** — iron plank, stone tablet, banner ribbon, gilded
   laurel, obsidian gems, marble serpent (epic SKUs include shimmer).
7. **Shop UI** — replace flag tab with badge tab + previews.
8. **Tests** — unit + integration + visual QA pass.
9. **Docs** — update `docs/ai_opponent.md` and any cosmetics docs that
   referenced flags; mark this plan **Implemented**.

---

## 11. Open Questions / Future Work

- Should defeated/AI kingdoms get a unique **NPC badge** SKU (not purchasable)?
- Should the badge cosmetic be **part of the conquered-kingdom inheritance**
  (winner adopts loser's badge for that territory)? Probably no — keep
  badges per owning player.
- Future: badge **fonts** as a separate cosmetic axis.
- Future: animated badges (full sprite-sheet) for legendary tier.
