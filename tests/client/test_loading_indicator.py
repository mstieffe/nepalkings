"""Tests for the shared loading indicator helper."""


def test_draw_loading_indicator_returns_drawn_box():
    import pygame
    from game.components.loading_indicator import draw_loading_indicator

    surface = pygame.Surface((360, 220), pygame.SRCALPHA)
    box = draw_loading_indicator(
        surface,
        pygame.Rect(0, 0, 360, 220),
        'Loading test data...',
        started_at_ms=pygame.time.get_ticks() - 200,
        title='Test Load',
    )
    assert box is not None
    assert box.width > 0
    assert box.height > 0