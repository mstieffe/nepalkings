# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Client test setup: dummy pygame display and correct working directory."""
import os
import sys
import pytest

# Point SDL at headless drivers so pygame.init() works without a display.
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

# The client code expects to run from the nepal_kings/ directory so that
# relative image paths (e.g. 'img/…') resolve correctly.
NEPAL_KINGS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'nepal_kings')
NEPAL_KINGS_DIR = os.path.abspath(NEPAL_KINGS_DIR)

# Add nepal_kings to the Python path so `from game.…` imports work.
if NEPAL_KINGS_DIR not in sys.path:
    sys.path.insert(0, NEPAL_KINGS_DIR)


@pytest.fixture(autouse=True, scope='session')
def _chdir_to_nepal_kings():
    """Change CWD to nepal_kings/ for the entire test session."""
    original = os.getcwd()
    os.chdir(NEPAL_KINGS_DIR)
    import pygame
    pygame.init()
    yield
    os.chdir(original)
