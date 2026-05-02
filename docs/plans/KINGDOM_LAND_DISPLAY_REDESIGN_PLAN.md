# Kingdom Map – Land Display Visual Redesign Plan

**Goal:** improve readability and visual polish of per-land overlays on the
kingdom map (`HexMap._draw_hex_details`) without changing any gameplay data
or interaction model.

All changes are confined to the client. No server / API / DB changes.

---

## 1. Scope (confirmed)

In scope:

1. Bottom **stat strip** combining gold rate + suit bonus into one pill.
2. **Tier corner ribbon** (top-left) with 1–4 mini stars, replacing the
   wide row of stars rendered above the hex.
3. Redesigned **defence-incomplete warning badge** — red circular pill with
   white `!` and a subtle alpha pulse.
4. **Owner chip** (colored dot + truncated username) on a dark pill.
5. **Flag handling change**: per-tile flag visible only when zoomed in;
   when zoomed out, show a **single flag per kingdom group** centered on
   the group (alongside the existing kingdom name badge).
6. **Progressive disclosure by zoom**:
   - `zoom ≥ 1.0`: tier ribbon, warning/shield corners, kingdom group flag
   - `zoom ≥ 1.5`: stat strip (icons only, no numbers), owner chip dot only
   - `zoom ≥ 2.0`: full numbers, owner chip with name, per-tile flag
7. **Hover inner ring** for clearer focus + shared `_draw_pill()` helper
   used by every badge so they read as one design family.
8. **Kingdom group badge** small offset (above geometric centre) +
   subtle drop shadow, and now anchors the group flag.

Out of scope:

- Hex tile fill/border colours, suit/tier palettes.
- Border skins / surface art (`hex_cosmetics`).
- Minimap.
- Land detail box panel.
- Server payload (`defence_incomplete`, `owner_style`, etc).

---

## 2. Visual layout (per tile, max-zoom reference)

```
         ┌── tier ribbon (top-left)         warning ! (top-right) ──┐
         │   ★★★                                              !     │
shield   │                                                          │
badge ──►│              [ kingdom name badge ]                      │
(when     │                                                          │
shielded) │                  (cosmetic surface art)                  │
         │                                                          │
         │   ╭──────────────────────────────╮       🚩 flag ◄──────┤
         │   │ ⛁ 12   ♠ +3                  │     (top-right cosmetic)
         │   ╰──────────────────────────────╯                       │
         │              ● username (owner chip, bottom-center)      │
         └──────────────────────────────────────────────────────────┘
```

Corner anchors (relative to hex center, hex size `sz`):

| Anchor          | Element                              |
|-----------------|--------------------------------------|
| top-left        | shield badge (existing)              |
| under shield    | tier ribbon (★1–4)                  |
| top-right       | warning `!` badge (when incomplete)  |
| right-mid       | per-tile flag (zoom ≥ 2.0)           |
| bottom-center   | stat strip pill, owner chip below it |
| group center    | kingdom-name badge + group flag      |

---

## 3. Code changes

### 3.1 `nepal_kings/config/kingdom_settings.py`

Add the following constants near the existing `HEX_*` block:

```python
# Progressive disclosure thresholds
HEX_MAP_LAND_INFO_MIN_ZOOM       = 1.5    # was 2.0 — icons appear here
HEX_MAP_LAND_NUMBERS_MIN_ZOOM    = 2.0    # numeric labels appear at/above this
HEX_MAP_PER_TILE_FLAG_MIN_ZOOM   = 2.0    # below this only group flag draws
HEX_MAP_OWNER_NAME_MIN_ZOOM      = 2.0    # below this only colored dot draws

# Shared pill design tokens
HEX_PILL_BG_CLR        = (18, 16, 13, 215)
HEX_PILL_BORDER_CLR    = (166, 142, 96)
HEX_PILL_BORDER_OWN    = (250, 221, 0)
HEX_PILL_RADIUS_PX     = max(2, int(0.004 * SCREEN_HEIGHT))
HEX_PILL_PAD_X         = max(3, int(0.004 * SCREEN_WIDTH))
HEX_PILL_PAD_Y         = max(1, int(0.003 * SCREEN_HEIGHT))

# Tier ribbon
HEX_TIER_RIBBON_BG     = (24, 20, 12, 220)
HEX_TIER_RIBBON_TIER_TINT = {
    1: (124, 188, 132),
    2: (216, 188, 96),
    3: (188, 132, 220),
    4: (224, 92, 96),
}
HEX_TIER_RIBBON_STAR_SZ_FACTOR = 0.06   # of hex sz; clamped to ≥3 px

# Warning badge
HEX_WARNING_BG_CLR     = (188, 36, 36, 230)
HEX_WARNING_BORDER_CLR = (255, 220, 200)
HEX_WARNING_TEXT_CLR   = (255, 255, 255)
HEX_WARNING_PULSE_HZ   = 1.4   # alpha pulse cycles per second

# Owner chip
HEX_OWNER_CHIP_BG       = (22, 20, 16, 210)
HEX_OWNER_CHIP_BORDER   = (140, 130, 110)
HEX_OWNER_CHIP_OWN_TXT  = (255, 238, 150)
HEX_OWNER_CHIP_OTHER_TXT = (220, 215, 200)
HEX_OWNER_CHIP_DOT_R_FACTOR = 0.07   # of hex sz

# Hover ring
HEX_HOVER_RING_CLR     = (255, 255, 255, 165)
HEX_HOVER_RING_W       = 2

# Kingdom group badge polish
HEX_GROUP_BADGE_OFFSET_Y = -0.18   # fraction of hex sz above geometric center
HEX_GROUP_BADGE_SHADOW_CLR = (0, 0, 0, 140)
HEX_GROUP_BADGE_SHADOW_OFFSET = (1, 2)
```

Notes:
- `HEX_LABEL_FONT_SIZE` and `HEX_ICON_SIZE` stay; reused by stat strip.
- Existing `HEX_MINE_BADGE_BG/_CLR` reused for the kingdom group badge.

### 3.2 `nepal_kings/game/components/hex_map.py`

Refactor `_draw_hex_details` into composable helpers. New private methods:

| Method                              | Purpose                                       |
|-------------------------------------|-----------------------------------------------|
| `_draw_pill(rect, *, role)`         | Shared rounded pill bg+border (`role` in `'default' / 'own' / 'warn' / 'shield'`). |
| `_draw_stat_strip(tile, scx, scy, sz, *, show_numbers)` | Bottom pill with coin+gold and suit+bonus; honours zoom-tier. |
| `_draw_tier_ribbon(tile, corners, sz)` | Top-left ribbon with mini stars tinted by tier. |
| `_draw_warning_badge(tile, scx, scy, sz, now_ms)` | Red `!` circle with sin-based alpha pulse using `pygame.time.get_ticks()`. |
| `_draw_owner_chip(tile, scx, scy, sz, *, show_name)` | Colored owner dot ± name pill at bottom-center. |
| `_draw_hover_ring(corners)`         | Thin inner-inset white-alpha polygon outline. |
| `_draw_group_flag(group, sz)`       | Single flag rendered at group centre (uses an aggregated representative tile's `flag_key`). |

Call order inside `_draw_hex_details(tile, scx, scy, sz)`:

```
zoom = self.zoom
now_ms = pygame.time.get_ticks()
sz_ok_icons   = zoom >= HEX_MAP_LAND_INFO_MIN_ZOOM and sz >= 18
sz_ok_numbers = zoom >= HEX_MAP_LAND_NUMBERS_MIN_ZOOM and sz >= 24
per_tile_flag = zoom >= HEX_MAP_PER_TILE_FLAG_MIN_ZOOM and sz >= 30
owner_name_ok = zoom >= HEX_MAP_OWNER_NAME_MIN_ZOOM and sz >= 30

if sz_ok_icons:
    self._draw_tier_ribbon(tile, corners, sz)
    self._draw_stat_strip(tile, scx, scy, sz, show_numbers=sz_ok_numbers)

if tile.kingdom_is_shielded and sz > 24:
    self._draw_shield_badge(tile, scx, scy, sz)            # existing, unchanged

if tile.defence_incomplete and sz_ok_icons:
    self._draw_warning_badge(tile, scx, scy, sz, now_ms)   # replaces broken.png blit

if tile.owner:
    self._draw_owner_chip(tile, scx, scy, sz,
                          show_name=owner_name_ok and not tile.is_mine)
    if per_tile_flag:
        self._draw_owner_flag(tile, scx, scy, sz)          # existing draw, gated by zoom

if tile is self.hovered_tile:
    self._draw_hover_ring(corners)
```

Removals from current `_draw_hex_details`:
- Top-row tier stars call (replaced by ribbon).
- Centered gold row (moved into stat strip).
- Suit-bonus row at `y + sz*0.15` (moved into stat strip).
- Bottom owner-username text (moved into owner chip).
- Inline broken.png blit (replaced by warning badge).

`_kingdom_badges()` returns groups already; extend it to also pick a
**representative `flag_key`** (most common owner_style flag_key in the
group). `_draw_kingdom_badges`:

- Apply `HEX_GROUP_BADGE_OFFSET_Y` so the badge sits above the centre tile.
- Pre-blit a shadow surface using `HEX_GROUP_BADGE_SHADOW_*`.
- After drawing the name pill, render the group flag to the right of the
  pill at a slightly larger size, but **only when** `zoom <
  HEX_MAP_PER_TILE_FLAG_MIN_ZOOM` (so we never get redundant per-tile + group
  flags simultaneously).

### 3.3 `_draw_pill` design

```python
def _draw_pill(self, rect, *, role='default'):
    """Render one rounded pill background+border. Returns inner rect."""
    bg = settings.HEX_PILL_BG_CLR
    border = {
        'default': settings.HEX_PILL_BORDER_CLR,
        'own':     settings.HEX_PILL_BORDER_OWN,
        'warn':    settings.HEX_WARNING_BORDER_CLR,
        'shield':  (140, 190, 255),
    }[role]
    radius = settings.HEX_PILL_RADIUS_PX
    surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(surf, bg, surf.get_rect(), border_radius=radius)
    pygame.draw.rect(surf, border, surf.get_rect(), 1, border_radius=radius)
    self.window.blit(surf, rect.topleft)
    return rect.inflate(-2 * settings.HEX_PILL_PAD_X,
                        -2 * settings.HEX_PILL_PAD_Y)
```

`_draw_shield_badge` is updated to call `_draw_pill(rect, role='shield')`
instead of its inline rounded rect — keeps the shield in the shared family.

### 3.4 Warning badge pulse

```python
def _draw_warning_badge(self, tile, scx, scy, sz, now_ms):
    r = max(6, int(sz * 0.18))
    cx = int(scx + sz * 0.55)
    cy = int(scy - sz * 0.55)
    phase = (now_ms / 1000.0) * settings.HEX_WARNING_PULSE_HZ * 2 * math.pi
    a = 200 + int(40 * math.sin(phase))   # 160..240
    bg = (*settings.HEX_WARNING_BG_CLR[:3], a)
    badge = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
    pygame.draw.circle(badge, bg, (r + 2, r + 2), r)
    pygame.draw.circle(badge, settings.HEX_WARNING_BORDER_CLR,
                       (r + 2, r + 2), r, 1)
    txt = self._tier_font.render('!', True, settings.HEX_WARNING_TEXT_CLR)
    badge.blit(txt, txt.get_rect(center=(r + 2, r + 2)))
    self.window.blit(badge, (cx - r - 2, cy - r - 2))
```

Note: kingdom screen already calls `pygame.display.update()` per frame, so
the alpha pulse animates naturally without further plumbing.

### 3.5 Hover ring

```python
def _draw_hover_ring(self, corners):
    inset = []
    cx = sum(p[0] for p in corners) / 6
    cy = sum(p[1] for p in corners) / 6
    for x, y in corners:
        inset.append((x + (cx - x) * 0.08, y + (cy - y) * 0.08))
    surf = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT),
                          pygame.SRCALPHA)
    pygame.draw.polygon(surf, settings.HEX_HOVER_RING_CLR, inset,
                        settings.HEX_HOVER_RING_W)
    self.window.blit(surf, (0, 0))
```

(Implementation will use a tight bounding-box surface, not full-screen, for
performance — sketch above is illustrative.)

---

## 4. Tests

Existing tests under `tests/client/` that touch `hex_map` (component
construction, hover/select, minimap) must still pass. New tests:

`tests/client/test_hex_map_overlays.py` (new file):

1. **`test_tier_ribbon_rendered_for_each_tier`** — mock minimal pygame
   surface, instantiate `HexMap` with one tile per tier 1–4, call
   `_draw_tier_ribbon`, assert no exception and that the number of stars
   drawn matches tier (count `pygame.draw.polygon` calls via monkeypatch).
2. **`test_warning_badge_drawn_only_when_incomplete`** — toggle
   `defence_incomplete` and assert the badge surface blit happens iff true.
3. **`test_warning_badge_alpha_pulses`** — call render twice with two
   different fake `now_ms` values and assert resulting alpha differs.
4. **`test_progressive_disclosure_zoom_thresholds`** — at zoom `1.0`,
   `1.5`, `2.0` confirm respectively: nothing, icons (no numbers),
   icons + numbers (assert via spying on `font.render` calls).
5. **`test_per_tile_flag_hidden_when_zoomed_out_group_flag_drawn`** —
   at zoom `1.0` confirm `_draw_owner_flag` not called per tile but a
   single flag is drawn next to the kingdom group badge.
6. **`test_owner_chip_shows_dot_only_at_low_zoom_and_name_at_high_zoom`**.
7. **`test_pill_helper_used_by_shield_warning_stat_strip`** — monkeypatch
   `_draw_pill` and assert it's invoked from each.
8. **`test_no_legacy_top_star_row`** — render once and confirm
   `_draw_tier_stars` is not called (method may be deleted; if kept for
   backward compat, assert it's unused at the call site).

All tests should follow existing client test conventions (see
`/memories/repo/client_tests_cwd_imports.md`): set `sys.path` and
`os.chdir` to `nepal_kings/` before importing settings/components, and use
a dummy display surface via `pygame.Surface` instead of `set_mode`.

---

## 5. Migration / cleanup

- `_draw_tier_stars` becomes private and is **kept** but only used internally
  by `_draw_tier_ribbon` for star polygons (single-star helper). The big
  top-row variant call site is removed.
- The `broken.png` raw load (`self._broken_icon_raw` and the `os.path.join`
  block in `__init__`) can be removed; warning badge is fully vector. If
  any other component still uses it, leave the load and just remove the
  blit. Quick grep confirms only `_draw_hex_details` blits it; the
  `LandDetailBox` separately loads its own broken icon.
- No config keys are removed; `HEX_MAP_LAND_INFO_MIN_ZOOM` is repurposed
  (lowered to 1.5) and the new `HEX_MAP_LAND_NUMBERS_MIN_ZOOM` takes the
  old `2.0` semantic.

---

## 6. Implementation order

1. Add new settings constants in `kingdom_settings.py`.
2. Add `_draw_pill` helper and migrate `_draw_shield_badge` to it (smallest
   change; verifies shared style).
3. Implement `_draw_tier_ribbon`; remove top-row star call.
4. Implement `_draw_stat_strip`; remove old gold + suit-bonus draws.
5. Implement `_draw_warning_badge`; remove broken.png blit.
6. Implement `_draw_owner_chip`; remove old bottom owner-username draw.
7. Gate `_draw_owner_flag` by `HEX_MAP_PER_TILE_FLAG_MIN_ZOOM`.
8. Extend `_kingdom_badges` to emit representative flag key; render group
   flag in `_draw_kingdom_badges` when zoomed out; apply offset+shadow.
9. Implement `_draw_hover_ring`.
10. Write/run new tests; fix any regressions in existing tests.
11. Manual smoke-test in-game at zoom 0.5 / 1.0 / 1.5 / 2.0 / 3.0 / 4.0.

---

## 7. Risks / mitigations

- **Performance**: extra per-tile pill surfaces increase blits. Mitigation:
  cache pill surfaces by `(role, w, h)` in a dict on `HexMap` (same pattern
  as `_scaled_icon_cache`).
- **Pulse causes flicker on slow hardware**: clamp alpha range to
  `[160, 240]` and use a 1.4 Hz cycle so changes are smooth even at 30 fps.
- **Group flag duplication**: ensure mutually exclusive guard
  (`per_tile_flag` vs `zoom < HEX_MAP_PER_TILE_FLAG_MIN_ZOOM` for group
  flag) so a kingdom never shows both at once.
- **Truncation of long usernames** in owner chip: use a width budget of
  `sz * 1.4` and truncate with an ellipsis (`…`).
