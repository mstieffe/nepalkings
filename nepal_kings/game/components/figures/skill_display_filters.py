# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from copy import copy
import re


def strip_duel_only_skill_description(
    text,
    *,
    hide_checkmate=False,
    hide_instant_charge=False,
):
    """Remove duel-only skill wording from a figure or family description."""
    cleaned = str(text or '')

    if hide_instant_charge:
        cleaned = re.sub(
            r'\s+that charges instantly into battle when placed on the field\.\s*',
            '. ',
            cleaned,
        )
        cleaned = re.sub(
            r'\s+that can advance immediately when placed on the field\.\s*',
            '. ',
            cleaned,
        )

    if hide_checkmate:
        cleaned = re.sub(
            r'\s*Triggers checkmate when defeated\.\s*',
            ' ',
            cleaned,
        )

    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = cleaned.replace(' .', '.')
    cleaned = cleaned.replace('..', '.')
    return cleaned


def filter_family_for_display(
    family,
    *,
    hide_checkmate=False,
    hide_instant_charge=False,
):
    """Return a shallow-copied family when duel-only text must be hidden."""
    if family is None:
        return None

    clean_description = strip_duel_only_skill_description(
        getattr(family, 'description', ''),
        hide_checkmate=hide_checkmate,
        hide_instant_charge=hide_instant_charge,
    )
    if clean_description == getattr(family, 'description', ''):
        return family

    display_family = copy(family)
    display_family.description = clean_description
    return display_family


def filter_figure_for_display(
    figure,
    *,
    hide_checkmate=False,
    hide_instant_charge=False,
):
    """Return a shallow-copied figure with duel-only display traits removed."""
    if figure is None:
        return None

    display_family = filter_family_for_display(
        getattr(figure, 'family', None),
        hide_checkmate=hide_checkmate,
        hide_instant_charge=hide_instant_charge,
    )
    clean_description = strip_duel_only_skill_description(
        getattr(figure, 'description', ''),
        hide_checkmate=hide_checkmate,
        hide_instant_charge=hide_instant_charge,
    )

    needs_copy = (
        display_family is not getattr(figure, 'family', None)
        or clean_description != getattr(figure, 'description', '')
        or (hide_checkmate and getattr(figure, 'checkmate', False))
        or (hide_instant_charge and getattr(figure, 'instant_charge', False))
    )
    if not needs_copy:
        return figure

    display_figure = copy(figure)
    display_figure.family = display_family
    display_figure.description = clean_description
    if hide_checkmate:
        display_figure.checkmate = False
    if hide_instant_charge:
        display_figure.instant_charge = False
    return display_figure
