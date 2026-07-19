# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Mappings between offensive and defensive figure sides."""


def get_opp_color(color):
    if color == "offensive":
        return "defensive"
    elif color == "defensive":
        return "offensive"
    else:
        return None


# Keep historical repr and pickle lookup behavior while utils.utils re-exports
# this canonical implementation.
get_opp_color.__module__ = 'utils.utils'
