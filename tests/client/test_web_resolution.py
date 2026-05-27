# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import os
from pathlib import Path
import tempfile


_ORIGINAL_HOME = os.environ.get("HOME")
os.environ["HOME"] = str(Path(tempfile.gettempdir()) / "nepalkings-pytest-home")

from main import _fit_16_9_rect, _select_web_resolution

if _ORIGINAL_HOME is None:
    os.environ.pop("HOME", None)
else:
    os.environ["HOME"] = _ORIGINAL_HOME


def test_iphone_se_modern_landscape_uses_smallest_mobile_canvas():
    """iPhone SE 2nd/3rd gen landscape viewport is 667x375 CSS px."""
    assert _fit_16_9_rect(667, 375) == (666, 375)
    assert _select_web_resolution(667, 375, mobile=True)[:3] == (854, 480, '1.6')


def test_iphone_se_first_generation_landscape_uses_smallest_mobile_canvas():
    """The original iPhone SE is even smaller at 568x320 CSS px."""
    assert _fit_16_9_rect(568, 320) == (568, 319)
    assert _select_web_resolution(568, 320, mobile=True)[:3] == (854, 480, '1.6')


def test_larger_mobile_viewport_can_use_middle_canvas_tier():
    assert _select_web_resolution(1024, 576, mobile=True)[:3] == (1024, 576, '1.5')


def test_desktop_web_keeps_full_hd_when_it_fits():
    assert _select_web_resolution(1920, 1080, mobile=False)[:3] == (1920, 1080, None)
