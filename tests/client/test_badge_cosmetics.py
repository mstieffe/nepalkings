def test_all_badges_render_long_name_without_clipping():
    from config import settings
    from game.components import badge_cosmetics

    font = settings.get_font(settings.FS_BODY, bold=True)
    text = 'Kingdom of the Northern Hills'

    for badge_key in settings.HEX_BADGE_STYLES:
        surf = badge_cosmetics.render_badge(
            badge_key, text, font,
            target_h=max(font.get_height() + 6, int(font.get_height() * 1.6)),
            shimmer_phase=4,
        )
        text_w, text_h = font.size(text)
        assert surf.get_width() > text_w
        assert surf.get_height() >= text_h


def test_flashy_badges_reserve_more_horizontal_room_for_name():
    from config import settings
    from game.components import badge_cosmetics

    font = settings.get_font(settings.FS_BODY, bold=True)
    text = 'Northern Hills'
    target_h = max(font.get_height() + 6, int(font.get_height() * 1.6))

    plain = badge_cosmetics.render_badge(
        'badge_plain', text, font, target_h=target_h, shimmer_phase=0)
    laurel = badge_cosmetics.render_badge(
        'badge_gilded_laurel', text, font, target_h=target_h, shimmer_phase=3)
    gems = badge_cosmetics.render_badge(
        'badge_obsidian_gems', text, font, target_h=target_h, shimmer_phase=3)
    serpent = badge_cosmetics.render_badge(
        'badge_marble_serpent', text, font, target_h=target_h, shimmer_phase=3)

    assert laurel.get_width() > plain.get_width()
    assert gems.get_width() > plain.get_width()
    assert serpent.get_width() > plain.get_width()