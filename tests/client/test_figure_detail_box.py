from types import SimpleNamespace


def _figure(figure_id, player_id, suit, field, battle_bonus=0):
    return SimpleNamespace(
        id=figure_id,
        player_id=player_id,
        suit=suit,
        family=SimpleNamespace(field=field),
        get_battle_bonus=lambda: battle_bonus,
    )


def _detail_box_for(figure, all_figures):
    from game.components.figure_detail_box import FigureDetailBox

    box = FigureDetailBox.__new__(FigureDetailBox)
    box.figure = figure
    box.game = SimpleNamespace(player_id=1)
    box.all_figures = all_figures
    return box


def test_potential_battle_bonus_uses_selected_figure_side():
    player_battle = _figure(10, 1, 'Hearts', 'military')
    player_support = _figure(11, 1, 'Hearts', 'castle', battle_bonus=7)
    opponent_battle = _figure(20, 2, 'Hearts', 'military')
    opponent_support = _figure(21, 2, 'Hearts', 'castle', battle_bonus=3)
    all_figures = [
        player_battle,
        player_support,
        opponent_battle,
        opponent_support,
    ]

    player_box = _detail_box_for(player_battle, all_figures)
    opponent_box = _detail_box_for(opponent_battle, all_figures)

    assert player_box._calculate_potential_battle_bonus() == 7
    assert opponent_box._calculate_potential_battle_bonus() == 3