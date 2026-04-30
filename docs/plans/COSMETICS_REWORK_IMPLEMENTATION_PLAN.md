# Kingdom Cosmetics Rework — Implementation Plan

Status: proposed
Scope: visual overhaul of hex surfaces and borders, + premium polish (vertex
ornaments, center emblems), + 3 new surfaces and 2 new borders. Pricing
unchanged. Must remain smooth in the web client against a remote server, so
all per-hex cosmetic art is rendered once into a cached `pygame.Surface` keyed
by `(skin_key, hex_size, owner_color)` and reused every frame.

---

## 1. Goals

1. Each surface clearly recolors and re-textures the entire hex — no more
   sparse stamps that leave the underlying tier fill dominant.
2. Each border has a distinct *structural* identity (rope, carved notches,
   spikes, gem inlay, dashed) — not just different colors.
3. Epic-tier cosmetics get visible premium polish:
   - vertex ornaments at the 6 corners of owned hexes (border-tied)
   - a faint center emblem watermark matching the surface theme
4. New cosmetic SKUs to expand the catalog without touching prices of existing
   ones.
5. No lag in the web/remote client → aggressive caching of rendered art.

Non-goals: animation/shimmer, glow rings, price rebalancing, custom artwork
files (still procedural pygame drawing).

---

## 2. Catalog changes

### 2.1 New cosmetic keys

Surfaces (3 new):

| key                | name              | rarity | price |
|--------------------|-------------------|--------|-------|
| `surface_grass`    | Verdant Grass     | common | 350   |
| `surface_marble`   | Veined Marble     | rare   | 1100  |
| `surface_lava`     | Molten Lava       | epic   | 2100  |

Borders (2 new):

| key                  | name              | rarity | price |
|----------------------|-------------------|--------|-------|
| `border_rope_braid`  | Rope Braid Border | common | 500   |
| `border_thorned`     | Thorned Border    | epic   | 2050  |

(Both files: `server/server_settings.py::KINGDOM_COSMETIC_CATALOG` and
`nepal_kings/config/kingdom_settings.py` skin dicts.)

### 2.2 Existing keys — redesigned (key names unchanged → existing buyers keep
their unlocks; only the rendered look improves)

Surfaces:
- `surface_plain` — unchanged.
- `surface_parchment` — aged paper gradient (warm ivory → tan), dense
  cross-hatched ink fibers (~40 short strokes), 4 corner ink stains, soft
  edge vignette. Center emblem: feather quill.
- `surface_stone` — full cobblestone tiling: ~14 irregular polygonal stones
  with darker mortar between them; subtle highlight on top edge of each
  stone. Center emblem: stone arch.
- `surface_snow` — icy gradient (pale cyan → white), tiled snowflake field
  (~12 flakes on a 3×4 jittered grid), frosted edge halo.  Center emblem:
  snowflake.
- `surface_forest` — dense leaf canopy (~60 overlapping ellipse leaves in 2
  green tones), dappled-light specks. Center emblem: oak leaf.
- `surface_dusk` — radial gradient (deep indigo edges → violet center),
  scattered starfield (~25 4-point stars in 2 sizes), crescent moon as
  emblem.

Borders:
- `border_simple_gold` — keep base, add small bead at each vertex.
- `border_royal_blue` — replaced with **double rope-twist**: two parallel
  thinner main lines offset perpendicular, with short alternating diagonal
  ticks between them simulating braid.
- `border_emerald_carved` — single thick main line with regularly-spaced
  perpendicular notches biting inward; small leaf flourish at each vertex.
- `border_obsidian` — angular zig-zag spike pattern along each edge; small
  rune glyph (3 line strokes) at each vertex.
- `border_ruby` — main bar with **3 gem cabochons** inset per edge (round,
  with darker rim and bright highlight dot); metallic outer frame.
- `border_silver` — precise **dashed double-line**: two parallel thin lines
  with 6 dashes per edge.

### 2.3 Premium polish

Vertex ornaments (border-tied, only when border rarity ≥ rare):
- rare borders: small filled circle (gem) at each shared vertex.
- epic borders: 5-point star outline at each shared vertex.

Center emblems (surface-tied, only when surface rarity ≥ rare):
- drawn at hex center as a faint silhouette (alpha ~70) at ~38% of hex size.
- shape determined by surface theme (see 2.2).

Non-rare/common cosmetics get neither, keeping the visual ladder clear.

---

## 3. Rendering architecture

### 3.1 New module: `nepal_kings/game/components/hex_cosmetics.py`

Pure helpers, no pygame globals. Public API:

```python
def render_surface(skin_key: str, hex_size: int) -> pygame.Surface
def render_border_overlay(skin_key: str, hex_size: int, owner_color) -> pygame.Surface
def vertex_ornament_surface(skin_key: str, hex_size: int) -> pygame.Surface | None
def center_emblem_surface(skin_key: str, hex_size: int) -> pygame.Surface | None
```

Each returns a per-pixel-alpha `pygame.Surface` of size `2*hex_size × 2*hex_size`
(or `hex_size`-sized for emblem) with the art drawn relative to a hex centered
at surface center. The hex shape mask is applied so blits are clipped correctly.

Internally each function uses an LRU cache:
```python
@functools.lru_cache(maxsize=64)
def _render_surface_cached(skin_key, hex_size): ...
```

Cache keys are tuples of immutable primitives → safe for `lru_cache`. Border
overlay is keyed by `(skin_key, hex_size, owner_color_tuple)` so we cache once
per kingdom color. Cache size 64 is enough for ≤8 zoom levels × ~8 distinct
skins.

### 3.2 Integration into `hex_map.py`

In `_draw_surface_skin` / `_draw_hex_base`:
- Replace inline `_draw_surface_pattern` calls with a single
  `surface.blit(render_surface(skin_key, sz), top_left)`.
- Existing fill + tier overlay still drawn first.

In `_draw_owner_border` (already restructured):
- Compute external + shared edges as today.
- Replace the 3-layer `_draw_capped_line` calls with a blit of
  `render_border_overlay(skin_key, sz, owner_color)`. The cached overlay
  contains every external edge already drawn with full thickness, motifs,
  and (for shared edges) inset per-edge masks. The shared-edge inset logic
  moves into the overlay generator.
- Vertex ornaments and the center emblem are blitted on top in the
  details pass (`_draw_hex_details`) so they sit above the surface but
  optionally below labels/flags.

Hex-shape clipping: build the polygon mask once via
`pygame.draw.polygon` on a separate alpha-mask surface, then
`surf.blit(mask, (0,0), special_flags=pygame.BLEND_RGBA_MULT)` to clip the
finished art to hex bounds.

### 3.3 Per-frame work after caching

For each visible hex per frame (web client worst case ~30-50 hexes):
- 1 fill draw (tier color)
- 1 cached surface blit
- 1 cached border-overlay blit
- 0–1 cached vertex-ornament blit (only owned hexes with rare/epic border)
- 0–1 cached emblem blit (only owned hexes with rare/epic surface)
- existing label/flag/icon work

That is fewer pygame ops per hex than today's per-frame line/circle storm,
so the web client should get faster, not slower.

### 3.4 Color strength

`HEX_OWNER_ALPHA` and surface overlay alphas raised to 180–215 range so
surfaces clearly recolor. Underlying tier fill still bleeds through ~15–25%
to keep tier readable on hover. Concrete values per skin set in step 5.

---

## 4. Files to change

| File | Change |
|------|--------|
| `nepal_kings/config/kingdom_settings.py` | Update `HEX_BORDER_SKINS`, `HEX_SURFACE_SKINS` with new keys, add `'rarity'` field, raise overlay alphas, add emblem/ornament metadata. |
| `server/server_settings.py` | Add 5 new entries in `KINGDOM_COSMETIC_CATALOG`. |
| `nepal_kings/game/components/hex_cosmetics.py` | **New** module with cached renderers. |
| `nepal_kings/game/components/hex_map.py` | Replace inline `_draw_surface_pattern` and per-edge border drawing with cached blits; add ornament/emblem pass; remove now-unused `_draw_surface_pattern` and parts of `_draw_capped_line` callsites that move into the overlay generator. Keep `_draw_capped_line` itself (used by the overlay generator). |
| `tests/client/test_hex_map.py` | Update existing tests that count `_draw_capped_line` calls (now happens inside the cached overlay generator, not per-frame). Add tests for: cache hit reuses surface, ornament drawn iff border rarity ≥ rare, emblem drawn iff surface rarity ≥ rare, hex mask clips art to hex polygon. |
| `tests/server/test_kingdom_config.py` | Add purchase tests for the 5 new SKUs. |
| `tests/client/test_kingdom_config_screen.py` | Verify new cosmetics appear in the shop list. |

No DB migration needed — cosmetics are stored as opaque string keys in
`Kingdom.surface_key` / `border_key` / `flag_key` already.

---

## 5. Detailed surface art specs (procedural)

For each surface the renderer:
1. Fills a `2*sz × 2*sz` alpha surface.
2. Paints a **base layer** (gradient or solid tint, alpha ~190).
3. Paints a **texture layer** (pattern repeating across the whole hex).
4. Paints **edge accents** (vignette / halo) where called for.
5. Multiplies by hex-shape alpha mask.

### `surface_stone` (rare)
- Base: solid `(180, 178, 172, 200)`.
- Texture: 14 irregular convex polygons (4-6 sides each) seeded
  deterministically from skin name; each filled with a per-stone shade
  jittered ±12 from base, dark mortar `(58, 56, 54, 220)` outlines 1-2 px.
- Highlight: 1px lighter line on the top edge of each stone for relief.
- Vignette: subtle dark gradient at edges.

### `surface_parchment` (common)
- Base: vertical gradient `(248, 232, 188, 210)` → `(232, 206, 152, 210)`.
- Texture: 40 cross-hatched ink strokes `(120, 78, 36, 90)` at two angles
  (15°, -15°), 1 px wide, length 0.10–0.20 sz.
- 4 corner ink stains: irregular blob at each of NW, NE, SW, SE corners.
- Edge vignette: warm brown alpha gradient.

### `surface_snow` (common)
- Base: radial gradient `(244, 252, 255, 215)` center → `(196, 226, 240, 215)` rim.
- Texture: 12 snowflakes on a 4×3 jittered grid covering the whole hex,
  each a 6-arm flake with side-arms (line strokes), color `(255, 255, 255, 230)`.
- Frost halo: 2 px white inner-edge ring at 50% alpha.

### `surface_forest` (rare)
- Base: solid `(38, 90, 52, 200)`.
- Texture: 60 overlapping ellipse leaves in two greens `(64, 132, 72)` and
  `(96, 170, 96)` at alpha 220, sizes 0.07–0.13 sz, rotated by deterministic
  angle. Drawn back-to-front for depth.
- Speckles: 20 yellow-green dapple dots `(220, 240, 160, 140)` for sun-through-
  canopy effect.

### `surface_dusk` (epic)
- Base: radial gradient `(60, 30, 110, 220)` center → `(20, 16, 50, 220)` rim.
- Texture: 25 4-point stars (golden `(245, 220, 130, 220)`) at two sizes,
  scattered uniformly with seeded jitter.
- Subtle violet glow band at upper third.
- Center emblem layer adds the crescent moon (handled by emblem renderer).

### `surface_grass` (new, common)
- Base: solid `(86, 142, 64, 205)`.
- Texture: 80 short blade strokes (1 px, 4–7 px long) at slight forward tilt
  in two greens; tiled across the whole hex.
- 6 micro-flowers: tiny colored dots (white/yellow) sprinkled.

### `surface_marble` (new, rare)
- Base: solid `(238, 234, 226, 210)`.
- Texture: 6 long flowing veins drawn as multi-segment polylines in
  `(120, 110, 130, 150)` with 1–2 px width; each starts at one hex edge and
  meanders across.
- Subtle warm spot in upper-third (gradient).

### `surface_lava` (new, epic)
- Base: radial gradient `(38, 14, 12, 220)` rim → `(110, 30, 14, 220)` center.
- Texture: 12 glowing crack polylines `(255, 154, 60, 230)` with 1 px lighter
  core `(255, 226, 130, 220)` over them; cracks spread from center outward.
- Ember speckles: 18 small glowing dots near the cracks.
- Center emblem: stylized flame.

---

## 6. Detailed border art specs (procedural)

Each border generator returns a transparent surface the size of the hex. It
draws each of 6 edges using the same primitives but with skin-specific style.
Existing inset logic for shared-edge pairs is preserved.

### `border_simple_gold` (default, common)
- Single 3-layer line (existing look).
- Vertex bead: 2 px gold dot per vertex.

### `border_royal_blue` (common) → **rope braid**
- Two parallel main lines at offsets ±0.35 × edge_thickness from edge axis.
- 5 short diagonal ticks per edge connecting the two strands, alternating
  direction. Highlight color `(210, 232, 255)` on the upper strand.

### `border_emerald_carved` (rare) → **carved notches**
- Single thick main line.
- 7 inward-perpendicular notches per edge, each `0.5 × thickness` deep,
  drawn in `outer` color → reads as carved gaps.
- Vertex flourish: small 3-petal leaf shape.
- Vertex ornament (rare): small filled circle.

### `border_obsidian` (rare) → **spikes + runes**
- Zig-zag spike pattern: replace the straight main line with a polyline that
  alternates `+thickness/2` and `-thickness/2` perpendicular every edge/8 step.
- Vertex glyph: 3-stroke rune (changes per vertex via seed).
- Vertex ornament (rare): small filled circle.

### `border_ruby` (epic) → **gem cabochons**
- Main thick bar in dark ruby outer + bright ruby main.
- 3 cabochons per edge at edge fractions 0.25, 0.50, 0.75:
  - outer dark ring `outer` color, radius `thickness × 0.9`
  - inner gem `main` color, radius `thickness × 0.7`
  - bright highlight dot `highlight` color at 30°-up offset, radius
    `thickness × 0.25`.
- Vertex ornament (epic): 5-point star outline.

### `border_silver` (common) → **dashed double-line**
- Two parallel thin lines at offsets ±0.4 × thickness.
- Each rendered as 6 dashes of length 0.10 × edge with 0.066 × edge gaps.

### `border_rope_braid` (new, common)
- Like `royal_blue` but tan/brown rope colors and 7 diagonal ticks.
- Ticks taper using cap circles.

### `border_thorned` (new, epic) → **thorny vine**
- Main line `(46, 28, 24)` outer, `(120, 80, 56)` main.
- Every 0.18 along edge: a small thorn — triangle perpendicular to edge,
  base on the line, tip pointing outward, 0.6 × thickness tall.
- Vertex ornament (epic): 5-point star outline.

---

## 7. Test plan

Updated unit tests (`tests/client/test_hex_map.py`):
- `test_surface_skin_blits_cached_surface`: monkey-patch
  `hex_cosmetics.render_surface` to return a sentinel and assert it is blitted
  exactly once per visible hex.
- `test_surface_renderer_uses_cache`: call `render_surface` twice with same
  args, assert second call returns same object (cache hit).
- `test_border_overlay_clipped_to_hex`: blit overlay onto known background
  and assert pixels outside hex polygon are unchanged.
- `test_vertex_ornament_only_for_rare_or_higher_border`: with `border_simple_gold`
  the renderer returns `None`; with `border_ruby` it returns a non-empty surface.
- `test_center_emblem_only_for_rare_or_higher_surface`: same as above for
  surfaces.
- Update `test_owner_border_skips_same_owner_internal_edge` and
  `test_owner_border_insets_edge_shared_with_other_land` to operate against
  the new overlay generator instead of `_draw_capped_line` call counts.
- Keep `test_render_layers_bases_before_borders_and_details`.

New server tests (`tests/server/test_kingdom_config.py`):
- Purchase + equip each of the 5 new keys; assert gold debit and
  `Kingdom.<field>_key` updates.
- Reject purchase of an unknown cosmetic key.

Manual visual smoke test plan: run the kingdom screen, equip each surface +
border combo, screenshot at 100% and 200% zoom. Compare against a small
checklist (full-coverage, distinct from neighbors, ornaments visible at
rare/epic only).

---

## 8. Rollout steps (in execution order)

1. Add `rarity` field to existing skin dicts in
   `nepal_kings/config/kingdom_settings.py` (mirror catalog).
2. Add 5 new keys to both client `kingdom_settings.py` and server
   `server_settings.py` catalog.
3. Create `nepal_kings/game/components/hex_cosmetics.py` with cached
   renderers and hex-mask clipping. Implement surfaces first, borders next,
   ornaments + emblems last. Each renderer covered by a focused unit test.
4. Refactor `hex_map.py` to use the new renderers; remove the old inline
   `_draw_surface_pattern` body once all callers migrate.
5. Update existing hex_map tests; add new ones from §7.
6. Add server-side purchase tests for the 5 new keys.
7. Visual smoke test at 100%, 150%, 200% zoom on local + remote server.
8. Update `docs/database_management.md` only if any migration is needed
   (none expected).

---

## 9. Risks & mitigations

- **Cache memory**: 64 cached surfaces × ~30 KB each ≈ 2 MB. Acceptable.
- **Hex-mask cost**: building the polygon mask once per (skin, size) is part
  of the cached render → no per-frame cost.
- **Web client font/timing differences**: rendering uses only `pygame.draw`
  primitives, no fonts/images, so behavior is identical between desktop and
  web.
- **Backward compatibility**: existing players' equipped key strings remain
  valid; only the rendered look changes. Existing unlock lists unaffected.
- **Discoverability**: the kingdom config screen already iterates the
  catalog, so the 5 new entries appear automatically.

---

## 10. Out of scope (explicitly deferred)

- Animation / shimmer / pulse.
- Glow ring around owned hex.
- Custom PNG art (still procedural).
- Price rebalancing.
- Per-tier-level cosmetic gating.
