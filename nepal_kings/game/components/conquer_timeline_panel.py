# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Conquer-only top panel rendered as a left-to-right timeline.

The panel draws one bubble per :class:`game.screens.conquer_flow.TimelineStep`
along the left side, connected by a horizontal timeline.  The active step
sits next to a wide info box on the right showing details, related assets,
confirm / next buttons, and a countdown ring for non-interactive steps.

Read-only: derives all state from the screen's game/field/shop snapshots.
The screen attaches click rects via ``screen._conquer_objective_action_rects``
just like the previous panel did.
"""

import math

import pygame

from config import settings
from game.components.battle_moves.battle_move_icon_renderer import draw_battle_move_icon
from game.screens.conquer_flow import derive_conquer_timeline


# Layout constants ---------------------------------------------------------

_PAD_X = 0.018
_PAD_Y = 0.010
_TITLE_BAR_H = 0.040
_BUBBLE_MIN_W = 96
_BUBBLE_MAX_W = 150
_BUBBLE_GAP = 14
_INFO_MIN_W = 320
_INFO_PAD = 12
_FIGURE_FRAME_FILL = 0.84

# Auto-advance hold for non-interactive steps (ms).
AUTO_ADVANCE_MS = 4000

_TONE_COLOR = {
    'neutral': (220, 200, 150),
    'action': (255, 211, 116),
    'waiting': (176, 209, 255),
    'good': (165, 235, 168),
    'warning': (255, 196, 124),
    'bad': (245, 154, 142),
}

_OWNER_COLOR = {
    'you': (245, 215, 95),
    '': (180, 168, 140),
}

_SEQUENCED_STEP_KINDS = (
    'overview',
    'prelude_own',
    'prelude_opp',
    'attacker',
    'counter',
    'defender',
    'to_battle',
)


def _owner_color(owner):
    if owner in _OWNER_COLOR:
        return _OWNER_COLOR[owner]
    return (220, 140, 120)  # opponent (any non-empty, non-'you' owner)


class ConquerTimelinePanel:
    """Render the conquer top panel as a sequenced timeline + info box."""

    def __init__(self, window):
        self.window = window
        self.title_font = settings.get_font(settings.FS_HEADING, bold=True)
        self.bubble_title_font = settings.get_font(
            max(11, int(settings.FS_TINY * 0.85)), bold=True)
        self.owner_font = settings.get_font(
            max(10, int(settings.FS_TINY * 0.72)), bold=True)
        self.sidenote_font = settings.get_font(
            max(10, int(settings.FS_TINY * 0.72)))
        self.info_headline_font = settings.get_font(
            settings.FS_HEADING, bold=True)
        self.info_body_font = settings.get_font(
            max(13, int(settings.FS_SMALL * 0.95)))
        self.button_font = settings.get_font(
            max(13, int(settings.FS_TINY)), bold=True)
        self.tooltip_font = settings.get_font(settings.TOOLTIP_FONT_SIZE)
        # active-step hover state
        self._step_hover = None
        self._spell_hover = None
        self._figure_hover = None
        self._card_back_cache = {}
        # Spell-replay coupling: lags the server's ``conquer_resolution_step`` by
        # one when a spell-driven step is currently being animated/active so the
        # tactics rail keeps showing the pre-mutation state until the spell
        # resolves on screen.
        self._displayed_step_offset = 0
        self._last_seen_server_step = 0

    def currently_resolved_step_index(self, screen=None):
        """Return the resolution step the client should currently mirror.

        At game start the tactics hand must reflect the player's configured
        battle moves — i.e. resolution step 0.  As each prelude/spell timeline
        bubble becomes ``active`` or ``completed`` (the user has seen it on
        screen for the first time), we permit one additional ``conquer_
        resolution_step`` to be revealed.  This produces the user-requested
        "transition for each change" while keeping the existing greyed-old /
        coloured-new visual treatment in the tactics rail.

        We cap at the server's authoritative step so that prelude bubbles
        that do not mutate tactics (Health Boost, Poison targeting figures,
        etc.) never overshoot the real number of mutations.
        """
        server_step = 0
        game = None
        if screen is not None:
            cached = getattr(screen, '_conquer_resolution_step_server', None)
            state = getattr(screen, 'state', None)
            game = getattr(state, 'game', None) if state else None
            if cached is not None:
                server_step = int(cached)
            else:
                server_step = int(getattr(game, 'conquer_resolution_step', 0) or 0)
        else:
            server_step = int(self._last_seen_server_step or 0)
        # Track the latest server step we have seen for parity.
        self._last_seen_server_step = max(self._last_seen_server_step, server_step)
        # Once the battle proper has started, reveal everything — spell
        # timeline beats are by definition all in the past. Live snapshots can
        # carry active round/turn fields even when ``battle_confirmed`` is
        # false or absent, so key off the active battle fields directly.
        if game is not None and (
            getattr(game, 'battle_turn_player_id', None) is not None
            or int(getattr(game, 'battle_round', 0) or 0) >= 1
        ):
            return max(0, server_step - int(self._displayed_step_offset or 0))
        # Count completed-or-active spell timeline bubbles seen so far. Each
        # acts as a gate that permits one additional resolution step to surface.
        # ``derive_display_steps`` is cached on a 20Hz cadence, so this loop
        # is cheap even though it runs many times per frame.
        spell_steps_seen = 0
        if screen is not None:
            try:
                steps = self.derive_display_steps(screen)
            except Exception:
                steps = []
            for step in steps:
                if getattr(step, 'kind', '') in ('prelude_own', 'prelude_opp', 'counter'):
                    if getattr(step, 'completed', False) or getattr(step, 'active', False):
                        spell_steps_seen += 1
        gated = min(server_step, spell_steps_seen)
        return max(0, gated - int(self._displayed_step_offset or 0))

    # ------------------------------------------------------------------ entry

    def draw(self, screen):
        screen._conquer_objective_action_rects = {}
        self._step_hover = None
        self._spell_hover = None
        self._figure_hover = None

        steps = self.derive_display_steps(screen)
        active_idx = self._active_index(steps)

        header_h = int(settings.SCREEN_HEIGHT * screen.HEADER_H_FACTOR)
        self._draw_panel_background(header_h)
        self._draw_title_bar(screen, header_h)

        # Timeline + info-box geometry
        title_h = int(settings.SCREEN_HEIGHT * _TITLE_BAR_H)
        pad_x = int(settings.SCREEN_WIDTH * _PAD_X)
        pad_y = int(settings.SCREEN_HEIGHT * _PAD_Y)
        body_top = title_h + 4
        body_bottom = header_h - pad_y
        body_h = body_bottom - body_top

        info_step = steps[active_idx] if active_idx is not None else None
        info_visible = info_step is not None

        # Only completed or active steps are rendered.  Pending future
        # steps are hidden until they become reachable.
        visible_indices = [i for i, s in enumerate(steps) if s.completed or s.active]
        n_visible = len(visible_indices)

        avail_w = settings.SCREEN_WIDTH - 2 * pad_x
        info_w = max(_INFO_MIN_W, int(avail_w * 0.35)) if info_visible else 0
        timeline_w = avail_w - info_w - (_BUBBLE_GAP if info_visible else 0)
        bubble_room = (
            timeline_w - _BUBBLE_GAP * (max(1, n_visible) - 1)
        ) // max(1, n_visible)
        compact_min_w = 68 if n_visible >= 8 else _BUBBLE_MIN_W
        bubble_w = max(54, min(_BUBBLE_MAX_W, bubble_room))
        if bubble_w < compact_min_w:
            needed = compact_min_w * n_visible + _BUBBLE_GAP * max(0, n_visible - 1)
            if needed <= timeline_w:
                bubble_w = compact_min_w

        line_y = body_top + body_h // 2

        # Bubbles (render before the connecting line segments so we know
        # exact positions; line segments are drawn afterwards in the gaps
        # between adjacent visible bubbles only — never across a bubble).
        bubble_rects = []
        x = pad_x
        for idx in visible_indices:
            step = steps[idx]
            rect = pygame.Rect(x, body_top, bubble_w, body_h)
            self._draw_bubble(screen, rect, step, idx == active_idx)
            bubble_rects.append(rect)
            x += bubble_w + _BUBBLE_GAP

        # Connecting line: draw segments only in the gaps between adjacent
        # visible bubbles so it never bleeds through bubble alpha.
        for i in range(len(bubble_rects) - 1):
            left_rect = bubble_rects[i]
            right_rect = bubble_rects[i + 1]
            seg_x1 = left_rect.right + 2
            seg_x2 = right_rect.left - 2
            if seg_x2 > seg_x1:
                pygame.draw.line(self.window, (110, 92, 60),
                                 (seg_x1, line_y), (seg_x2, line_y), 2)

        # Info box (right of timeline)
        if info_visible:
            info_rect = pygame.Rect(
                pad_x + timeline_w + _BUBBLE_GAP, body_top,
                info_w, body_h)
            self._draw_info_box(screen, info_rect, info_step, active_idx, steps)

    def draw_within(self, screen, rect, right_reserve=0):
        """Render the full timeline body inside ``rect`` without a title bar.

        Used by the persistent two-row header (pre-battle inline view) and
        by the hover-expansion overlay that grows the timeline row only.
        The rect's caller already painted the persistent top row, so this
        method skips the title bar entirely. ``right_reserve`` keeps timeline
        content clear of persistent timer/chevron chrome while the panel
        background and bottom border still span the full rect.
        """
        self._step_hover = None
        self._spell_hover = None
        self._figure_hover = None

        if rect.width <= 32 or rect.height <= 24:
            return

        # Solid panel background + bottom border for legibility.
        panel = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        panel.fill((19, 18, 16, 240))
        self.window.blit(panel, rect.topleft)
        pygame.draw.line(self.window, (189, 149, 75),
                         (rect.left, rect.bottom - 1),
                         (rect.right, rect.bottom - 1), 2)

        steps = self.derive_display_steps(screen)
        active_idx = self._active_index(steps)

        pad_x = max(8, int(settings.SCREEN_WIDTH * _PAD_X))
        pad_y = max(4, int(settings.SCREEN_HEIGHT * _PAD_Y))
        body_top = rect.top + pad_y
        body_bottom = rect.bottom - pad_y
        body_h = max(0, body_bottom - body_top)

        info_step = steps[active_idx] if active_idx is not None else None
        info_visible = info_step is not None

        visible_indices = [i for i, s in enumerate(steps) if s.completed or s.active]
        n_visible = len(visible_indices)
        if n_visible == 0:
            return

        content_width = max(0, rect.width - max(0, int(right_reserve)))
        avail_w = max(0, content_width - 2 * pad_x)
        info_w = max(_INFO_MIN_W, int(avail_w * 0.35)) if info_visible else 0
        if info_w >= avail_w - 80:
            # Fall back to a body-only layout when the rect is too narrow
            # to host the info box without crushing the bubbles.
            info_w = 0
            info_visible = False
        timeline_w = avail_w - info_w - (_BUBBLE_GAP if info_visible else 0)
        bubble_room = (
            timeline_w - _BUBBLE_GAP * (max(1, n_visible) - 1)
        ) // max(1, n_visible)
        compact_min_w = 68 if n_visible >= 8 else _BUBBLE_MIN_W
        bubble_w = max(54, min(_BUBBLE_MAX_W, bubble_room))
        if bubble_w < compact_min_w:
            needed = compact_min_w * n_visible + _BUBBLE_GAP * max(0, n_visible - 1)
            if needed <= timeline_w:
                bubble_w = compact_min_w

        line_y = body_top + body_h // 2

        bubble_rects = []
        x = rect.left + pad_x
        for idx in visible_indices:
            step = steps[idx]
            bubble_rect = pygame.Rect(x, body_top, bubble_w, body_h)
            self._draw_bubble(screen, bubble_rect, step, idx == active_idx)
            bubble_rects.append(bubble_rect)
            x += bubble_w + _BUBBLE_GAP

        for i in range(len(bubble_rects) - 1):
            left_rect = bubble_rects[i]
            right_rect = bubble_rects[i + 1]
            seg_x1 = left_rect.right + 2
            seg_x2 = right_rect.left - 2
            if seg_x2 > seg_x1:
                pygame.draw.line(self.window, (110, 92, 60),
                                 (seg_x1, line_y), (seg_x2, line_y), 2)

        if info_visible:
            info_rect = pygame.Rect(
                rect.left + pad_x + timeline_w + _BUBBLE_GAP,
                body_top, info_w, body_h)
            self._draw_info_box(screen, info_rect, info_step, active_idx, steps)

    def draw_collapsed_strip(self, screen, rect):
        # Reset hover state every frame so tooltips disappear immediately
        # when the timeline collapses (or the mouse leaves the strip).
        self._step_hover = None
        self._spell_hover = None
        self._figure_hover = None
        steps = [
            step for step in self.derive_display_steps(screen)
            if step.completed or step.active
        ]
        if not steps or rect.width <= 16 or rect.height <= 14:
            return

        gap = max(5, min(8, rect.height // 9))
        icon_size = min(42, max(20, rect.height - 10))
        needed = len(steps) * icon_size + max(0, len(steps) - 1) * gap
        if needed > rect.width:
            min_icon_size = 14
            max_icons = max(1, (rect.width + gap) // (min_icon_size + gap))
            if len(steps) > max_icons:
                steps = steps[-max_icons:]
            icon_size = max(
                min_icon_size,
                (rect.width - gap * max(0, len(steps) - 1)) // len(steps),
            )
            needed = len(steps) * icon_size + max(0, len(steps) - 1) * gap
        x = rect.left + max(0, (rect.width - needed) // 2)
        y = rect.centery - icon_size // 2
        line_y = rect.centery

        for idx, step in enumerate(steps):
            icon_rect = pygame.Rect(x, y, icon_size, icon_size)
            if idx:
                pygame.draw.line(
                    self.window,
                    (100, 82, 54),
                    (icon_rect.left - gap + 1, line_y),
                    (icon_rect.left - 1, line_y),
                    1,
                )
            border = (
                _TONE_COLOR.get(step.tone, _TONE_COLOR['neutral'])
                if step.active else (145, 116, 66)
            )
            pygame.draw.rect(self.window, (24, 22, 18), icon_rect, border_radius=5)
            pygame.draw.rect(
                self.window, border, icon_rect,
                2 if step.active else 1,
                border_radius=5,
            )
            self._draw_step_icon(screen, icon_rect.inflate(-4, -4), step)
            if icon_rect.collidepoint(pygame.mouse.get_pos()):
                self._step_hover = (step, icon_rect)
            x += icon_size + gap

    # --------------------------------------------------------------- backgrounds

    def _draw_panel_background(self, header_h):
        rect = pygame.Rect(0, 0, settings.SCREEN_WIDTH, header_h)
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((19, 18, 16, 240))
        self.window.blit(panel, rect.topleft)
        pygame.draw.line(self.window, (189, 149, 75),
                         (0, header_h - 1),
                         (settings.SCREEN_WIDTH, header_h - 1), 2)

    def _draw_title_bar(self, screen, header_h):
        title_h = int(settings.SCREEN_HEIGHT * _TITLE_BAR_H)
        game = screen.state.game
        tier = getattr(game, 'land_tier', None) if game else None
        opponent = (getattr(game, 'opponent_name', None) or 'Defender') if game else 'Defender'
        land = f'Tier {tier} Land' if tier else 'Conquer Battle'
        title = f'{land} vs {opponent}'

        title_x = int(settings.SCREEN_WIDTH * _PAD_X)
        title_y = max(6, (title_h - self.title_font.get_height()) // 2)
        title_surf = self.title_font.render(title, True, (246, 222, 170))
        self.window.blit(title_surf, (title_x, title_y))

        # Withdraw button (right edge) when allowed
        if self._withdraw_available(screen):
            wd_w = int(settings.SCREEN_WIDTH * 0.072)
            wd_h = max(26, int(settings.SCREEN_HEIGHT * 0.030))
            wd_x = settings.SCREEN_WIDTH - int(settings.SCREEN_WIDTH * _PAD_X) - wd_w
            wd_y = (title_h - wd_h) // 2
            rect = pygame.Rect(wd_x, wd_y, wd_w, wd_h)
            screen._conquer_objective_action_rects['withdraw'] = rect
            self._draw_rect_button(rect, 'Withdraw', (93, 52, 48))

    @staticmethod
    def _withdraw_available(screen):
        game = screen.state.game
        if not game or getattr(game, 'game_over', False) or getattr(game, 'state', None) == 'finished':
            return False
        if getattr(screen, '_withdraw_dialogue_open', False):
            return False
        try:
            return bool(screen._is_current_player_conquer_attacker())
        except Exception:
            return False

    # ----------------------------------------------------- step derivation

    def _derive_steps(self, screen):
        game = screen.state.game
        field = screen.subscreens.get('field') if hasattr(screen, 'subscreens') else None
        shop = screen.subscreens.get('battle_shop') if hasattr(screen, 'subscreens') else None
        return derive_conquer_timeline(game, screen.state, field, shop)

    def derive_display_steps(self, screen):
        # Hot path: this function is called many times per frame (tactics
        # rail, ledger, duel lane, active-step lookups). Each call walks
        # the entire conquer flow and runs sequence-gate timing, which
        # was the dominant source of frame lag. Cache by (screen,
        # game data version, server step, ticks bucket) so repeated
        # within-frame calls reuse the same result while still allowing
        # the hold-timer to advance at a smooth 20Hz cadence.
        game = getattr(getattr(screen, 'state', None), 'game', None)
        ticks = pygame.time.get_ticks() if game is not None else 0
        cache_key = (
            id(screen),
            getattr(game, '_game_data_version', None) if game else None,
            getattr(game, 'battle_round', None) if game else None,
            getattr(game, 'battle_confirmed', None) if game else None,
            getattr(game, 'battle_turn_player_id', None) if game else None,
            getattr(screen, '_conquer_resolution_step_server', None),
            ticks // 50,  # 20Hz cadence for hold-timer progress
        )
        cached = getattr(self, '_display_steps_cache', None)
        if cached is not None and cached[0] == cache_key:
            return cached[1]
        steps = self._derive_steps(screen)
        steps = self._apply_sequence_gates(screen, steps)
        battle_steps = getattr(screen, '_conquer_battle_timeline_steps', None)
        if callable(battle_steps):
            steps = battle_steps(steps)
        self._display_steps_cache = (cache_key, steps)
        return steps

    def _apply_sequence_gates(self, screen, steps):
        """Hold resolved sequence beats on screen before later beats appear.

        The server can legitimately advance multiple conquer states inside a
        single poll (for example: opponent prelude -> defender selection).  The
        timeline keeps those resolved beats readable by promoting the earliest
        unacknowledged completed beat to the active info panel until its timer
        expires or the player presses Next.
        """
        acked = getattr(screen, '_conquer_acknowledged_step_kinds', None)
        if acked is None:
            acked = set()
            screen._conquer_acknowledged_step_kinds = acked
        timers = getattr(screen, '_conquer_timeline_step_started_at', None)
        if timers is None:
            timers = {}
            screen._conquer_timeline_step_started_at = timers

        game = getattr(getattr(screen, 'state', None), 'game', None)
        if game and (
            getattr(game, 'state', None) == 'finished'
            or getattr(game, 'game_over', False)
            or getattr(game, 'battle_turn_player_id', None) is not None
            or int(getattr(game, 'battle_round', 0) or 0) >= 1
            or getattr(game, 'last_battle_result', None)):
            return steps

        now = pygame.time.get_ticks()
        for idx, step in enumerate(steps):
            if step.active and step.interactive:
                for later in steps[idx + 1:]:
                    later.active = False
                    later.completed = False
                return steps

            if not self._step_needs_hold(step):
                continue
            if step.kind in acked:
                step.active = False
                step.completed = True
                continue

            started = timers.get(step.kind)
            if started is None:
                timers[step.kind] = now
                started = now
            if now - started >= AUTO_ADVANCE_MS:
                acked.add(step.kind)
                step.active = False
                step.completed = True
                continue

            step.active = True
            step.completed = False
            step.interactive = False
            step.primary_action = 'next'
            for later in steps[idx + 1:]:
                later.active = False
                later.completed = False
            return steps
        return steps

    @staticmethod
    def _step_needs_hold(step):
        if step.kind not in _SEQUENCED_STEP_KINDS:
            return False
        if step.interactive:
            return False
        if not (step.completed or step.active):
            return False
        if step.kind == 'overview':
            return True
        if step.kind.startswith('prelude'):
            return step.icon_kind == 'spell'
        if step.kind in ('attacker', 'defender'):
            return step.icon_kind == 'figure'
        return True

    @staticmethod
    def _active_index(steps):
        for idx, step in enumerate(steps):
            if step.active:
                return idx
        return None

    # ----------------------------------------------------- bubble rendering

    def _draw_bubble(self, screen, rect, step, is_active):
        # Background tinting depends on completed/active state
        if is_active:
            bg = (36, 30, 22, 245)
            border = _TONE_COLOR.get(step.tone, _TONE_COLOR['neutral'])
            border_w = 2
        elif step.completed:
            bg = (28, 26, 22, 220)
            border = (150, 122, 70)
            border_w = 1
        else:
            bg = (22, 20, 18, 200)
            border = (84, 72, 50)
            border_w = 1
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        surf.fill(bg)
        self.window.blit(surf, rect.topleft)
        pygame.draw.rect(self.window, border, rect, border_w, border_radius=6)

        if is_active:
            self._draw_pulse_ring(rect)

        inner_pad = 6
        cursor_y = rect.top + inner_pad

        # Title (top)
        title = step.title or ''
        title_surf = self.bubble_title_font.render(
            self._fit(title, self.bubble_title_font, rect.width - 2 * inner_pad),
            True, (235, 220, 180))
        self.window.blit(
            title_surf,
            (rect.centerx - title_surf.get_width() // 2, cursor_y))
        cursor_y += title_surf.get_height() + 2

        # Owner pill
        if step.owner:
            owner_label = step.owner.upper()
            color = _owner_color(step.owner.lower() if step.owner.lower() in _OWNER_COLOR else step.owner)
            pill_text = self.owner_font.render(
                self._fit(owner_label, self.owner_font, rect.width - 2 * inner_pad - 8),
                True, (24, 22, 18))
            pad_x = 6
            pill_w = pill_text.get_width() + pad_x * 2
            pill_h = pill_text.get_height() + 4
            pill_rect = pygame.Rect(
                rect.centerx - pill_w // 2, cursor_y, pill_w, pill_h)
            pygame.draw.rect(self.window, color, pill_rect, border_radius=8)
            self.window.blit(pill_text,
                             (pill_rect.left + pad_x, pill_rect.top + 2))
            cursor_y = pill_rect.bottom + 4

        # Icon area (centered)
        icon_bottom = rect.bottom - inner_pad - (
            self.sidenote_font.get_height() + 2 if step.sidenote else 0)
        icon_h = max(28, icon_bottom - cursor_y - 4)
        icon_rect = pygame.Rect(
            rect.centerx - icon_h // 2, cursor_y, icon_h, icon_h)
        if icon_rect.right > rect.right - inner_pad:
            icon_rect.width = rect.right - inner_pad - icon_rect.left
            icon_rect.height = icon_rect.width
        self._draw_step_icon(screen, icon_rect, step)

        # Sidenote at bottom
        if step.sidenote:
            note_surf = self.sidenote_font.render(
                self._fit(step.sidenote, self.sidenote_font,
                          rect.width - 2 * inner_pad),
                True, (210, 196, 156))
            self.window.blit(
                note_surf,
                (rect.centerx - note_surf.get_width() // 2,
                 rect.bottom - note_surf.get_height() - 3))

        # Completion checkmark badge (top-right)
        if step.completed and not is_active:
            badge_r = 8
            cx = rect.right - badge_r - 3
            cy = rect.top + badge_r + 3
            pygame.draw.circle(self.window, (90, 150, 100), (cx, cy), badge_r)
            pygame.draw.circle(self.window, (210, 240, 210), (cx, cy), badge_r, 1)
            # check mark
            pygame.draw.lines(
                self.window, (245, 255, 240), False,
                [(cx - 3, cy), (cx - 1, cy + 3), (cx + 4, cy - 3)], 2)

        if rect.collidepoint(pygame.mouse.get_pos()):
            self._step_hover = (step, rect)

    def _draw_step_icon(self, screen, rect, step):
        kind = step.icon_kind
        if kind == 'land':
            self._draw_land_icon(rect, step.icon_payload or {})
        elif kind == 'spell':
            self._draw_spell_icon(screen, rect, step.icon_payload, step.sub_icons)
        elif kind == 'figure':
            payload = step.icon_payload or {}
            self._draw_figure_icon(screen, rect, payload.get('figure'),
                                   payload.get('side', 'opponent'),
                                   bool(payload.get('reveal', False)))
        elif kind == 'tactic':
            self._draw_tactic_icon(screen, rect, step.icon_payload)
        elif kind == 'go':
            self._draw_go_icon(rect, step.completed, step.active)
        else:
            self._draw_silhouette(rect)

    def _draw_tactic_icon(self, screen, rect, payload):
        if isinstance(payload, dict) and 'moves' in payload:
            self._draw_paired_tactic_icons(screen, rect, payload.get('moves') or ())
            return

        move = payload.get('move') if isinstance(payload, dict) else payload
        if not isinstance(move, dict) or not move.get('family_name'):
            self._draw_silhouette(rect)
            return
        self._draw_single_tactic_icon(screen, rect, move)

    def _draw_paired_tactic_icons(self, screen, rect, moves):
        if not isinstance(moves, (list, tuple)):
            moves = ()
        pair = list(moves[:2])
        while len(pair) < 2:
            pair.append(None)
        gap = max(2, rect.width // 12)
        icon_size = max(10, min(rect.height, (rect.width - gap) // 2))
        total_w = icon_size * 2 + gap * (len(pair) - 1)
        x = rect.centerx - total_w // 2
        y = rect.centery - icon_size // 2
        colors = ((245, 215, 95), (220, 140, 120))
        for idx, move in enumerate(pair):
            icon_rect = pygame.Rect(
                x + idx * (icon_size + gap), y,
                icon_size, icon_size,
            )
            if isinstance(move, dict) and move.get('family_name'):
                self._draw_single_tactic_icon(screen, icon_rect, move)
            else:
                self._draw_silhouette(icon_rect)
            pygame.draw.rect(self.window, colors[idx], icon_rect, 1, border_radius=5)

    def _draw_single_tactic_icon(self, screen, rect, move):
        icon_size = max(8, min(rect.width, rect.height))
        try:
            glow_cache, icon_cache, frame_cache, suit_icon_cache, icon_font = (
                screen._conquer_battle_move_icon_assets(icon_size))
            draw_battle_move_icon(
                self.window,
                rect.centerx,
                rect.centery,
                move.get('family_name', ''),
                move.get('suit', ''),
                0 if move.get('family_name') == 'Block' else int(move.get('value') or 0),
                glow_cache,
                icon_cache,
                frame_cache,
                suit_icon_cache,
                icon_font,
                icon_size,
                hovered=False,
                is_used=False,
                suit_b=move.get('suit_b'),
            )
        except Exception:
            pygame.draw.rect(self.window, (64, 57, 47), rect, border_radius=6)
            letter = self.bubble_title_font.render(
                (move.get('family_name') or '?')[:1], True, (230, 210, 160))
            self.window.blit(letter, letter.get_rect(center=rect.center))
            pygame.draw.rect(self.window, (184, 142, 71), rect, 1, border_radius=6)

    def _draw_land_icon(self, rect, payload):
        tier = payload.get('tier')
        suit = payload.get('suit') or ''
        bg_rect = rect.inflate(-4, -4)
        pygame.draw.rect(self.window, (60, 50, 36), bg_rect, border_radius=8)
        pygame.draw.rect(self.window, (165, 130, 70), bg_rect, 1, border_radius=8)
        if tier:
            txt = self.bubble_title_font.render(
                f'T{tier}', True, (250, 230, 180))
            self.window.blit(txt, txt.get_rect(center=(bg_rect.centerx, bg_rect.centery - 6)))
        if suit:
            sub = self.sidenote_font.render(
                suit[:6], True, (220, 200, 160))
            self.window.blit(sub, sub.get_rect(center=(bg_rect.centerx, bg_rect.centery + 8)))

    def _draw_spell_icon(self, screen, rect, name, sub_names):
        images = (screen._get_spell_icon_image(name)
                  if name and hasattr(screen, '_get_spell_icon_image') else [])
        if images:
            img = pygame.transform.smoothscale(images[0], (rect.w, rect.h))
            self.window.blit(img, rect)
        else:
            pygame.draw.rect(self.window, (64, 57, 47), rect, border_radius=6)
            letter = self.bubble_title_font.render(
                (name or '?')[:1], True, (230, 210, 160))
            self.window.blit(letter, letter.get_rect(center=rect.center))
        pygame.draw.rect(self.window, (184, 142, 71), rect, 1, border_radius=6)
        if rect.collidepoint(pygame.mouse.get_pos()) and name:
            self._spell_hover = (name, rect)
        # Sub-icons stacked below if any (small)
        if sub_names:
            small = max(14, rect.height // 3)
            x = rect.right - small
            y = rect.bottom - small
            for sn in sub_names:
                sub_imgs = (screen._get_spell_icon_image(sn)
                            if hasattr(screen, '_get_spell_icon_image') else [])
                if sub_imgs:
                    sub_img = pygame.transform.smoothscale(sub_imgs[0], (small, small))
                    self.window.blit(sub_img, (x, y))
                pygame.draw.rect(self.window, (184, 142, 71),
                                 pygame.Rect(x, y, small, small), 1, border_radius=3)
                x -= small + 2

    def _draw_figure_icon(self, screen, rect, figure, side, reveal):
        if figure is None:
            self._draw_silhouette(rect)
            return
        layout = self._figure_art_layout(rect, figure, reveal)
        if layout is not None:
            frame_src, frame_rect, icon_src, icon_rect = layout
            frame_img = pygame.transform.smoothscale(frame_src, frame_rect.size)
            if reveal and icon_src is not None and icon_rect is not None:
                icon_img = pygame.transform.smoothscale(icon_src, icon_rect.size)
                self.window.blit(icon_img, icon_rect)
            self.window.blit(frame_img, frame_rect)
            # card-back overlay for hidden figures
            if not reveal:
                cards = getattr(figure, 'cards', []) or []
                if cards:
                    cards_to_show = cards[:3]
                    inner_w = max(8, frame_rect.width - 8)
                    spacing = 2
                    cb_size = (inner_w - spacing * (len(cards_to_show) - 1)) // max(1, len(cards_to_show))
                    cb_size = max(4, min(cb_size, frame_rect.height // 4))
                    cb = self._get_card_back(cb_size)
                    if cb is not None:
                        total_w = len(cards_to_show) * cb_size + (len(cards_to_show) - 1) * spacing
                        sx = frame_rect.centerx - total_w // 2
                        cy = frame_rect.bottom - cb_size - max(2, frame_rect.height // 14)
                        for i in range(len(cards_to_show)):
                            self.window.blit(cb, (sx + i * (cb_size + spacing), cy))
            if reveal and frame_rect.collidepoint(pygame.mouse.get_pos()):
                self._figure_hover = (figure, frame_rect, side)
        else:
            if not reveal:
                self._draw_hidden_figure_back(
                    self._figure_fallback_rect(rect),
                    getattr(figure, 'cards', []) or [],
                )
            else:
                self._draw_silhouette(self._figure_fallback_rect(rect))

    @classmethod
    def _figure_art_layout(cls, rect, figure, reveal):
        family = getattr(figure, 'family', None)
        frame_visible = getattr(family, 'frame_img', None)
        frame_hidden = (getattr(family, 'frame_hidden_img', None)
                        or getattr(family, 'frame_closed_img', None)
                        or frame_visible)
        frame_src = frame_visible if reveal else frame_hidden
        if frame_src is None:
            return None

        frame_side = max(1, int(min(rect.width, rect.height) * _FIGURE_FRAME_FILL))
        frame_size = cls._scale_size_to_fit(frame_src, frame_side, frame_side)
        frame_rect = pygame.Rect(0, 0, *frame_size)
        frame_rect.center = rect.center

        icon_src = None
        icon_rect = None
        if reveal:
            icon_src = (getattr(family, 'icon_img_small', None)
                        or getattr(family, 'icon_img', None))
            if icon_src is not None:
                icon_side = max(1, int(frame_side / settings.FRAME_FIGURE_SCALE))
                icon_size = cls._scale_size_to_fit(icon_src, icon_side, icon_side)
                icon_rect = pygame.Rect(0, 0, *icon_size)
                icon_rect.center = frame_rect.center
        return frame_src, frame_rect, icon_src, icon_rect

    @staticmethod
    def _scale_size_to_fit(surface, max_width, max_height):
        src_w = max(1, surface.get_width())
        src_h = max(1, surface.get_height())
        scale = min(max_width / src_w, max_height / src_h)
        return (max(1, int(src_w * scale)), max(1, int(src_h * scale)))

    @staticmethod
    def _figure_fallback_rect(rect):
        side = max(1, int(min(rect.width, rect.height) * _FIGURE_FRAME_FILL))
        fallback = pygame.Rect(0, 0, side, side)
        fallback.center = rect.center
        return fallback

    def _draw_go_icon(self, rect, completed, active):
        color = (165, 235, 168) if completed else (
            (255, 211, 116) if active else (130, 110, 76))
        pygame.draw.polygon(
            self.window, color,
            [(rect.left + 8, rect.top + 8),
             (rect.right - 6, rect.centery),
             (rect.left + 8, rect.bottom - 8)])
        pygame.draw.polygon(
            self.window, (24, 22, 18),
            [(rect.left + 8, rect.top + 8),
             (rect.right - 6, rect.centery),
             (rect.left + 8, rect.bottom - 8)], 2)

    def _draw_silhouette(self, rect):
        inset = rect.inflate(-6, -6)
        surf = pygame.Surface(inset.size, pygame.SRCALPHA)
        pygame.draw.rect(surf, (60, 55, 45, 160), surf.get_rect(),
                         border_radius=6)
        self.window.blit(surf, inset.topleft)
        pygame.draw.rect(self.window, (90, 80, 60), inset, 1,
                         border_radius=6)
        txt = self.sidenote_font.render('—', True, (140, 130, 110))
        self.window.blit(txt, txt.get_rect(center=inset.center))

    def _draw_hidden_figure_back(self, rect, cards):
        pygame.draw.rect(self.window, (42, 37, 31), rect, border_radius=6)
        pygame.draw.rect(self.window, (116, 92, 58), rect, 1, border_radius=6)
        count = max(1, min(3, len(cards) if cards else 1))
        card_w = max(10, min(rect.width // 3, int(rect.height * 0.34)))
        card_h = max(14, int(card_w * 1.35))
        total_w = count * card_w + (count - 1) * 3
        x = rect.centerx - total_w // 2
        y = rect.centery - card_h // 2
        back = self._get_card_back(min(card_w, card_h))
        for i in range(count):
            card_rect = pygame.Rect(x + i * (card_w + 3), y, card_w, card_h)
            if back is not None:
                img = pygame.transform.smoothscale(back, card_rect.size)
                self.window.blit(img, card_rect)
            else:
                pygame.draw.rect(self.window, (68, 56, 42), card_rect, border_radius=3)
            pygame.draw.rect(self.window, (184, 142, 71), card_rect, 1, border_radius=3)

    def _draw_pulse_ring(self, rect):
        t = pygame.time.get_ticks() / 1000.0
        pulse = 0.5 + 0.5 * math.sin(t * 3.0)
        alpha = int(60 + 100 * pulse)
        ring = pygame.Surface((rect.w + 8, rect.h + 8), pygame.SRCALPHA)
        pygame.draw.rect(
            ring, (245, 205, 95, alpha),
            ring.get_rect(), 3, border_radius=8)
        self.window.blit(ring, (rect.left - 4, rect.top - 4))

    def _get_card_back(self, size):
        if size in self._card_back_cache:
            return self._card_back_cache[size]
        try:
            raw = pygame.image.load(
                settings.CARD_IMG_PATH + 'back.png').convert_alpha()
        except Exception:
            self._card_back_cache[size] = None
            return None
        scaled = pygame.transform.smoothscale(raw, (size, size))
        self._card_back_cache[size] = scaled
        return scaled

    # -------------------------------------------------------- info box

    def _draw_info_box(self, screen, rect, step, active_idx, steps):
        # Frame
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        surf.fill((28, 26, 22, 230))
        self.window.blit(surf, rect.topleft)
        border = _TONE_COLOR.get(step.tone, _TONE_COLOR['neutral'])
        pygame.draw.rect(self.window, border, rect, 2, border_radius=8)

        x = rect.left + _INFO_PAD
        y = rect.top + _INFO_PAD
        max_w = rect.width - 2 * _INFO_PAD

        # Headline
        headline = step.info_headline or step.title
        for line in self._wrap(headline, self.info_headline_font, max_w, 2):
            s = self.info_headline_font.render(line, True, border)
            self.window.blit(s, (x, y))
            y += s.get_height() + 1
        y += 4

        # Body
        assets = tuple(getattr(step, 'info_assets', ()) or ())
        btn_h = max(28, int(settings.SCREEN_HEIGHT * 0.030))
        button_top = rect.bottom - btn_h - _INFO_PAD
        asset_bottom = button_top - 8
        min_asset_h = min(92, max(44, rect.height // 3)) if assets else 0
        body_bottom_limit = (asset_bottom - min_asset_h) if assets else (button_top - 6)
        max_body_lines = 4 if assets else 6
        if step.info_body:
            for line in self._wrap(step.info_body, self.info_body_font, max_w, max_body_lines):
                if y + self.info_body_font.get_height() > body_bottom_limit:
                    break
                s = self.info_body_font.render(line, True, (224, 214, 188))
                self.window.blit(s, (x, y))
                y += s.get_height() + 2

        if assets:
            y = max(y + 6, rect.top + _INFO_PAD)
            self._draw_info_assets(screen, rect, y, asset_bottom, assets)

        # Countdown ring for non-interactive steps
        countdown_ratio = self._step_countdown_ratio(screen, step)
        if countdown_ratio is not None and not step.interactive:
            self._draw_countdown(rect, countdown_ratio)

        # Buttons (bottom row)
        self._draw_active_buttons(screen, rect, step)

    def _draw_info_assets(self, screen, rect, start_y, bottom_limit, assets):
        layout = self._layout_info_asset_rects(rect, start_y, bottom_limit, assets)
        if not layout:
            return
        clip_rect = pygame.Rect(
            rect.left + _INFO_PAD,
            max(rect.top + _INFO_PAD, start_y),
            max(0, rect.width - 2 * _INFO_PAD),
            max(0, bottom_limit - max(rect.top + _INFO_PAD, start_y)),
        )
        if clip_rect.width <= 0 or clip_rect.height <= 0:
            return
        previous_clip = self.window.get_clip()
        self.window.set_clip(clip_rect)
        try:
            for asset, asset_rect in layout:
                kind = asset.get('kind')
                if kind == 'resource':
                    self._draw_resource_asset(
                        asset_rect,
                        asset.get('label', ''), asset.get('value', ''),
                        asset.get('tone', 'neutral'),
                    )
                    continue
                if kind == 'card':
                    self._draw_card_asset(screen, asset_rect, asset.get('card'),
                                          bool(asset.get('reveal', True)),
                                          label=asset.get('label', ''),
                                          tone=asset.get('tone', 'neutral'),
                                          dim=bool(asset.get('dim', False)),
                                          crossed=bool(asset.get('crossed', False)))
                elif kind == 'spell':
                    self._draw_spell_icon(screen, asset_rect, asset.get('name'), ())
                elif kind == 'figure':
                    self._draw_figure_icon(
                        screen, asset_rect,
                        asset.get('figure'),
                        asset.get('side', 'opponent'),
                        bool(asset.get('reveal', False)),
                    )
                elif kind == 'tactic':
                    self._draw_tactic_icon(
                        screen, asset_rect, {'move': asset.get('move')})
        finally:
            self.window.set_clip(previous_clip)

    def _layout_info_asset_rects(self, rect, start_y, bottom_limit, assets):
        usable_assets = [a for a in assets[:10] if isinstance(a, dict)]
        if not usable_assets:
            return []

        gap = 6
        min_size = 20
        max_size = 42
        left = rect.left + _INFO_PAD
        right = rect.right - _INFO_PAD
        max_w = max(0, right - left)
        available_h = max(0, bottom_limit - start_y)
        if max_w <= 0 or available_h < min_size:
            return []

        max_rows = max(1, min(3, (available_h + gap) // (min_size + gap)))
        best_layout = None
        best_score = None
        for rows in range(1, max_rows + 1):
            row_size = min(max_size, (available_h - gap * (rows - 1)) // rows)
            for size in range(row_size, min_size - 1, -2):
                layout = self._pack_info_asset_rects(
                    usable_assets, left, right, start_y, rows, size, gap)
                if layout is None:
                    continue
                score = (size, -rows)
                if best_score is None or score > best_score:
                    best_score = score
                    best_layout = layout
                break
        if best_layout is not None:
            return best_layout
        return self._pack_info_asset_rects(
            usable_assets, left, right, start_y, max_rows, min_size, gap,
            allow_partial=True,
        ) or []

    def _pack_info_asset_rects(self, assets, left, right, start_y, rows, size,
                               gap, *, allow_partial=False):
        layout = []
        x = left
        y = start_y
        row = 1
        max_w = max(0, right - left)
        for asset in assets:
            kind = asset.get('kind')
            width = self._info_asset_width(kind, size, max_w, asset)
            height = min(28, size) if kind == 'resource' else size
            if layout and x + width > right:
                row += 1
                if row > rows:
                    return layout if allow_partial else None
                x = left
                y += size + gap
            if width <= 0 or x + width > right:
                return layout if allow_partial else None
            layout.append((asset, pygame.Rect(x, y, width, height)))
            x += width + gap
        return layout

    def _info_asset_width(self, kind, size, max_width, asset=None):
        if kind == 'resource':
            label = (asset.get('label', '') if isinstance(asset, dict) else '') or ''
            value = (asset.get('value', '') if isinstance(asset, dict) else '') or ''
            text = f'{label}: {value}' if value != '' else str(label)
            text_w = self.sidenote_font.size(text)[0] if text else 0
            # Hug content; keep a small floor so empty/very short chips
            # still feel like chips, and never exceed the row width.
            return min(max_width, max(64, text_w + 16))
        if kind == 'card':
            return max(18, int(size * 0.82))
        return min(max_width, size)

    def _draw_card_asset(self, screen, rect, card_data, reveal, *,
                         label='', tone='neutral', dim=False, crossed=False):
        if not reveal:
            back = self._get_card_back(min(rect.width, rect.height))
            if back is not None:
                img = pygame.transform.smoothscale(back, rect.size)
                self.window.blit(img, rect)
            else:
                pygame.draw.rect(self.window, (48, 42, 35), rect, border_radius=4)
            pygame.draw.rect(self.window, (184, 142, 71), rect, 1, border_radius=4)
            return
        if not isinstance(card_data, dict):
            self._draw_silhouette(rect)
            return
        try:
            from game.components.cards.card import Card
            card = Card(
                rank=card_data.get('rank'),
                suit=card_data.get('suit'),
                value=card_data.get('value', 0),
                id=card_data.get('id'),
                type=card_data.get('type', 'main'),
            )
            icon = card.make_icon(self.window, getattr(screen.state, 'game', None), 0, 0)
            src = icon.front_img
            scale = min(rect.width / src.get_width(), rect.height / src.get_height())
            img = pygame.transform.smoothscale(
                src,
                (max(8, int(src.get_width() * scale)),
                 max(8, int(src.get_height() * scale))),
            )
            self.window.blit(img, img.get_rect(center=rect.center))
        except Exception:
            pygame.draw.rect(self.window, (64, 57, 47), rect, border_radius=4)
            rank_label = str(card_data.get('rank', '?')) if isinstance(card_data, dict) else '?'
            txt = self.sidenote_font.render(rank_label, True, (230, 210, 160))
            self.window.blit(txt, txt.get_rect(center=rect.center))
        if dim:
            shade = pygame.Surface(rect.size, pygame.SRCALPHA)
            shade.fill((18, 16, 14, 112))
            self.window.blit(shade, rect.topleft)
        if crossed:
            cross_color = (220, 72, 62)
            pygame.draw.line(
                self.window, cross_color,
                (rect.left + 2, rect.top + 2),
                (rect.right - 2, rect.bottom - 2), 3)
            pygame.draw.line(
                self.window, cross_color,
                (rect.right - 2, rect.top + 2),
                (rect.left + 2, rect.bottom - 2), 3)
        if label:
            color = _TONE_COLOR.get(tone, _TONE_COLOR['neutral'])
            label_font = self.sidenote_font
            label_text = self._fit(str(label), label_font, max(8, rect.width - 4))
            label_surf = label_font.render(label_text, True, (24, 22, 18))
            label_rect = label_surf.get_rect()
            label_rect.inflate_ip(6, 3)
            label_rect.midbottom = (rect.centerx, rect.bottom - 1)
            pygame.draw.rect(self.window, color, label_rect, border_radius=5)
            self.window.blit(label_surf, label_surf.get_rect(center=label_rect.center))
        pygame.draw.rect(self.window, (184, 142, 71), rect, 1, border_radius=4)

    def _draw_resource_asset(self, rect, label, value, tone):
        color = _TONE_COLOR.get(tone, _TONE_COLOR['neutral'])
        pygame.draw.rect(self.window, (50, 45, 36), rect, border_radius=6)
        pygame.draw.rect(self.window, color, rect, 1, border_radius=6)
        text = f'{label}: {value}' if value != '' else str(label)
        # Chips are sized to fit the full text in _info_asset_width; only
        # apply truncation as a last-resort safety when the rect is forced
        # narrower than the desired width.
        rendered_text = text
        if self.sidenote_font.size(text)[0] > rect.width - 8:
            rendered_text = self._fit(text, self.sidenote_font, rect.width - 8)
        surf = self.sidenote_font.render(rendered_text, True, (236, 224, 190))
        self.window.blit(surf, surf.get_rect(center=rect.center))

    def _step_countdown_ratio(self, screen, step):
        """Return remaining-time ratio in [0, 1] for non-interactive auto-advance."""
        if step.interactive:
            return None
        timers = getattr(screen, '_conquer_timeline_step_started_at', None)
        if timers is None:
            return None
        now = pygame.time.get_ticks()
        started = timers.get(step.kind)
        if started is None:
            timers[step.kind] = now
            started = now
        elapsed = now - started
        return max(0.0, min(1.0, 1.0 - elapsed / float(AUTO_ADVANCE_MS)))

    def _draw_countdown(self, rect, ratio):
        """Small countdown arc in the top-right of the info box."""
        size = 22
        cx = rect.right - size - 6
        cy = rect.top + size // 2 + 6
        pygame.draw.circle(self.window, (60, 50, 36), (cx, cy), size // 2)
        pygame.draw.circle(self.window, (165, 130, 70), (cx, cy), size // 2, 1)
        # arc representing remaining time
        end_angle = -math.pi / 2 + 2 * math.pi * ratio
        pygame.draw.arc(
            self.window, (255, 211, 116),
            pygame.Rect(cx - size // 2, cy - size // 2, size, size),
            -math.pi / 2, end_angle, 2)

    def _draw_active_buttons(self, screen, rect, step):
        pending = getattr(screen, '_conquer_pending_confirmation', None)
        btn_h = max(28, int(settings.SCREEN_HEIGHT * 0.030))
        btn_w = max(96, int(rect.width * 0.30))
        btn_y = rect.bottom - btn_h - _INFO_PAD
        x_left = rect.left + _INFO_PAD

        if pending and step.kind in ('attacker', 'defender'):
            confirm_rect = pygame.Rect(x_left, btn_y, btn_w, btn_h)
            cancel_rect = pygame.Rect(x_left + btn_w + 10, btn_y, btn_w, btn_h)
            self._draw_rect_button(confirm_rect, 'Confirm', (77, 119, 71))
            self._draw_rect_button(cancel_rect, 'Cancel', (92, 75, 63))
            screen._conquer_objective_action_rects['confirm'] = confirm_rect
            screen._conquer_objective_action_rects['cancel'] = cancel_rect
            return

        if step.interactive:
            # Selection-based interaction (target on field) — no buttons,
            # just a hint.
            hint = self.info_body_font.render(
                'Use the field to select.',
                True, (200, 195, 175))
            self.window.blit(hint, (x_left, btn_y + 4))
            return

        # Auto-advance: Next button to skip the countdown.
        next_rect = pygame.Rect(x_left, btn_y, btn_w, btn_h)
        self._draw_rect_button(next_rect, 'Next', (86, 106, 134))
        screen._conquer_objective_action_rects['next'] = next_rect

    # ------------------------------------------------------------ tooltips

    def draw_hover_tooltips(self, screen):
        self._draw_hover_tooltips(screen)

    def _draw_hover_tooltips(self, screen):
        if self._step_hover:
            step, anchor = self._step_hover
            self._draw_step_info_tooltip(screen, step, anchor)
            return
        if self._spell_hover:
            self._draw_spell_tooltip(*self._spell_hover)
        if self._figure_hover:
            self._draw_figure_tooltip(*self._figure_hover)

    def _draw_step_info_tooltip(self, screen, step, anchor):
        pad_x = settings.TOOLTIP_PAD_X
        pad_y = settings.TOOLTIP_PAD_Y
        line_gap = 3
        section_gap = 6
        box_w = min(
            max(300, int(settings.SCREEN_WIDTH * 0.34)),
            settings.SCREEN_WIDTH - 8,
        )
        content_w = max(40, box_w - pad_x * 2)
        headline = step.info_headline or step.title or ''
        headline_lines = self._wrap(headline, self.info_headline_font, content_w, 2)
        body_lines = self._wrap(step.info_body or '', self.info_body_font, content_w, 5)
        assets = tuple(getattr(step, 'info_assets', ()) or ())

        headline_h = self._lines_height(
            headline_lines, self.info_headline_font, line_gap)
        body_h = self._lines_height(body_lines, self.info_body_font, line_gap)
        asset_h = self._step_tooltip_asset_height(box_w, assets) if assets else 0

        content_h = headline_h
        if body_lines:
            content_h += section_gap + body_h
        if assets and asset_h:
            content_h += section_gap + asset_h

        box_h = min(settings.SCREEN_HEIGHT - 8, content_h + pad_y * 2)
        rect = self._tooltip_rect(anchor, box_w, box_h)

        border = _TONE_COLOR.get(step.tone, settings.TOOLTIP_BORDER_COLOR)
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.TOOLTIP_BG_COLOR, surf.get_rect(),
                         border_radius=settings.TOOLTIP_CORNER_R)
        pygame.draw.rect(surf, border, surf.get_rect(),
                         settings.TOOLTIP_BORDER_WIDTH,
                         border_radius=settings.TOOLTIP_CORNER_R)
        self.window.blit(surf, rect.topleft)

        y = rect.top + pad_y
        for line in headline_lines:
            rendered = self.info_headline_font.render(line, True, border)
            self.window.blit(rendered, (rect.left + pad_x, y))
            y += rendered.get_height() + line_gap
        if headline_lines:
            y += section_gap - line_gap

        for line in body_lines:
            rendered = self.info_body_font.render(line, True, (224, 214, 188))
            self.window.blit(rendered, (rect.left + pad_x, y))
            y += rendered.get_height() + line_gap
        if body_lines:
            y += section_gap - line_gap

        if assets and asset_h:
            asset_bottom = min(rect.bottom - pad_y, y + asset_h)
            self._draw_info_assets(screen, rect, y, asset_bottom, assets)

    def _step_tooltip_asset_height(self, box_w, assets):
        probe_rect = pygame.Rect(0, 0, box_w, 160)
        layout = self._layout_info_asset_rects(probe_rect, 0, 150, assets)
        if not layout:
            return 0
        return max(asset_rect.bottom for _asset, asset_rect in layout)

    @staticmethod
    def _lines_height(lines, font, line_gap):
        if not lines:
            return 0
        return len(lines) * font.get_height() + (len(lines) - 1) * line_gap

    @staticmethod
    def _tooltip_rect(anchor, box_w, box_h):
        box_x = anchor.centerx - box_w // 2
        box_y = anchor.bottom + 6
        box_x = max(4, min(box_x, settings.SCREEN_WIDTH - box_w - 4))
        if box_y + box_h > settings.SCREEN_HEIGHT - 4:
            above_y = anchor.top - box_h - 6
            box_y = above_y if above_y >= 4 else settings.SCREEN_HEIGHT - box_h - 4
        box_y = max(4, min(box_y, settings.SCREEN_HEIGHT - box_h - 4))
        return pygame.Rect(box_x, box_y, box_w, box_h)

    def _draw_spell_tooltip(self, name, anchor):
        self._render_tooltip_lines([(name, (255, 240, 190))], anchor)

    def _draw_figure_tooltip(self, figure, anchor, side):
        lines = []
        name = getattr(figure, 'name', '?')
        suit = (getattr(figure, 'suit', '') or '').capitalize()
        try:
            base_power = figure.get_value() if hasattr(figure, 'get_value') else 0
        except Exception:
            base_power = 0
        enchantments = getattr(figure, 'active_enchantments', []) or []
        try:
            enchant_mod = sum(e.get('power_modifier', 0) for e in enchantments)
        except Exception:
            enchant_mod = 0
        total_power = base_power + enchant_mod
        power_str = f'Power: {total_power}'
        if enchant_mod:
            sign = '+' if enchant_mod > 0 else ''
            power_str += f'  ({base_power} {sign}{enchant_mod} enchant)'
        lines.append((name, (255, 235, 170)))
        lines.append((f'{suit}  •  {power_str}', (210, 210, 190)))
        skills = []
        if hasattr(figure, 'get_active_skills'):
            try:
                skills = [label for _key, label in figure.get_active_skills()]
            except Exception:
                pass
        if skills:
            lines.append(('Skills: ' + ', '.join(skills), (190, 220, 240)))
        self._render_tooltip_lines(lines, anchor)

    def _render_tooltip_lines(self, lines, anchor):
        pad_x = settings.TOOLTIP_PAD_X
        pad_y = settings.TOOLTIP_PAD_Y
        line_gap = 3
        rendered = [self.info_body_font.render(t, True, c) for t, c in lines]
        max_w = max(s.get_width() for s in rendered)
        total_h = sum(s.get_height() for s in rendered) + line_gap * (len(rendered) - 1)
        box_w = max_w + pad_x * 2
        box_h = total_h + pad_y * 2
        box_x = anchor.centerx - box_w // 2
        box_y = anchor.bottom + 6
        box_x = max(4, min(box_x, settings.SCREEN_WIDTH - box_w - 4))
        box_y = min(box_y, settings.SCREEN_HEIGHT - box_h - 4)
        rect = pygame.Rect(box_x, box_y, box_w, box_h)
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.TOOLTIP_BG_COLOR, surf.get_rect(),
                         border_radius=settings.TOOLTIP_CORNER_R)
        pygame.draw.rect(surf, settings.TOOLTIP_BORDER_COLOR, surf.get_rect(),
                         settings.TOOLTIP_BORDER_WIDTH,
                         border_radius=settings.TOOLTIP_CORNER_R)
        self.window.blit(surf, rect.topleft)
        y = rect.top + pad_y
        for s in rendered:
            self.window.blit(s, (rect.left + pad_x, y))
            y += s.get_height() + line_gap

    # ------------------------------------------------------------ helpers

    def _draw_rect_button(self, rect, label, color):
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse)
        bg = tuple(min(255, c + 24) for c in color) if hovered else color
        pygame.draw.rect(self.window, bg, rect, border_radius=6)
        pygame.draw.rect(self.window, (238, 219, 172), rect, 1, border_radius=6)
        text = self.button_font.render(label, True, (255, 244, 216))
        self.window.blit(text, text.get_rect(center=rect.center))

    def _wrap(self, text, font, max_width, max_lines=2):
        words = (text or '').split()
        if not words:
            return []
        lines = []
        current = ''
        for word in words:
            trial = word if not current else current + ' ' + word
            if font.size(trial)[0] <= max_width:
                current = trial
                continue
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
        if current and len(lines) < max_lines:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
        if len(lines) == max_lines and words:
            lines[-1] = self._fit(lines[-1], font, max_width)
        return lines

    def _fit(self, text, font, max_width):
        text = text or ''
        if font.size(text)[0] <= max_width:
            return text
        clipped = text
        ellipsis = '…'
        while clipped and font.size(clipped + ellipsis)[0] > max_width:
            clipped = clipped[:-1]
        return clipped + ellipsis if clipped else ellipsis
