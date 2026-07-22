# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Inline text rendering that replaces written card suits with suit icons."""

from __future__ import annotations

import re
from typing import List, Tuple

import pygame

from config import settings


SUIT_NAMES = ('Hearts', 'Diamonds', 'Clubs', 'Spades')
_SUIT_KEYS = frozenset(value.lower() for value in SUIT_NAMES)
_SUIT_PATTERN = re.compile(r'\b(Hearts|Diamonds|Clubs|Spades)\b', re.IGNORECASE)
_RAW_ICON_CACHE = {}
_SCALED_ICON_CACHE = {}


def contains_suit_name(text) -> bool:
    return bool(_SUIT_PATTERN.search(str(text or '')))


def load_suit_icon(suit, size):
    """Load one of the canonical suit assets at ``size`` pixels."""
    name = str(suit or '').lower()
    if name not in _SUIT_KEYS:
        return None
    size = max(1, int(size))
    key = (name, size)
    cached = _SCALED_ICON_CACHE.get(key)
    if cached is not None:
        return cached
    raw = _RAW_ICON_CACHE.get(name)
    if raw is None:
        try:
            raw = pygame.image.load(
                settings.SUIT_ICON_IMG_PATH + name + '.png')
            try:
                raw = raw.convert_alpha()
            except pygame.error:
                pass
            _RAW_ICON_CACHE[name] = raw
        except Exception:
            return None
    icon = pygame.transform.smoothscale(raw, (size, size))
    _SCALED_ICON_CACHE[key] = icon
    return icon


def _icon_size(font, icon_size=None):
    if icon_size is not None:
        return max(1, int(icon_size))
    # The source PNGs carry a little transparent breathing room, so use a box
    # roughly as tall as the text line to keep the visible pip legible.
    return max(10, int(font.get_height() * 1.05))


def _parts(text):
    value = str(text or '')
    parts = []
    cursor = 0
    for match in _SUIT_PATTERN.finditer(value):
        if match.start() > cursor:
            parts.append(('text', value[cursor:match.start()]))
        parts.append(('suit', match.group(1)))
        cursor = match.end()
    if cursor < len(value):
        parts.append(('text', value[cursor:]))
    return parts


def _segments(text, font, color, icon_size=None):
    size = _icon_size(font, icon_size)
    segments = []
    for kind, value in _parts(text):
        if kind == 'suit':
            icon = load_suit_icon(value, size)
            if icon is not None:
                segments.append(icon)
        else:
            segments.append(font.render(value, True, color))
    if not segments:
        segments.append(font.render('', True, color))
    return segments


def suit_text_size(text, font, icon_size=None) -> Tuple[int, int]:
    size = _icon_size(font, icon_size)
    width = 0
    height = font.get_height()
    for kind, value in _parts(text):
        if kind == 'suit':
            width += size
            height = max(height, size)
        else:
            text_size = font.size(value)
            width += text_size[0]
            height = max(height, text_size[1])
    return width, height


def fit_suit_text(text, font, max_width, icon_size=None):
    """Ellipsize text using rendered icon widths for any suit tokens."""
    value = str(text or '')
    max_width = max(0, int(max_width))
    if suit_text_size(value, font, icon_size)[0] <= max_width:
        return value
    ellipsis = '…'
    clipped = value
    while clipped and suit_text_size(
            clipped.rstrip() + ellipsis, font, icon_size)[0] > max_width:
        clipped = clipped[:-1]
    clipped = clipped.rstrip()
    # Never expose a partially-clipped written suit (``Diam…``). If the cut
    # lands inside a canonical name, drop that entire token; only a complete
    # name can reach the renderer, where it becomes an icon.
    for match in _SUIT_PATTERN.finditer(value):
        if match.start() < len(clipped) < match.end():
            clipped = clipped[:match.start()].rstrip()
            break
    return clipped + ellipsis if clipped else ellipsis


def wrap_suit_text(text, font, max_width, max_lines=2, icon_size=None) -> List[str]:
    """Word-wrap while measuring written suits at their icon width."""
    words = str(text or '').split()
    if not words or max_lines <= 0 or max_width <= 0:
        return []
    lines = []
    word_index = 0
    while word_index < len(words) and len(lines) < max_lines:
        current = words[word_index]
        word_index += 1
        while word_index < len(words):
            trial = current + ' ' + words[word_index]
            if suit_text_size(trial, font, icon_size)[0] > max_width:
                break
            current = trial
            word_index += 1
        lines.append(fit_suit_text(current, font, max_width, icon_size))
    if word_index < len(words) and lines:
        lines[-1] = fit_suit_text(
            lines[-1].rstrip('…') + '…', font, max_width, icon_size)
        if not lines[-1].endswith('…'):
            lines[-1] += '…'
    return lines


def render_suit_text(text, font, color, *, max_width=None, icon_size=None):
    """Return a transparent surface with suit words replaced by icons."""
    value = str(text or '')
    if max_width is not None:
        value = fit_suit_text(value, font, max_width, icon_size)
    segments = _segments(value, font, color, icon_size)
    width = max(1, sum(segment.get_width() for segment in segments))
    height = max(1, max(
        (segment.get_height() for segment in segments),
        default=font.get_height(),
    ))
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    x = 0
    for segment in segments:
        y = (height - segment.get_height()) // 2
        surface.blit(segment, (x, y))
        x += segment.get_width()
    return surface
