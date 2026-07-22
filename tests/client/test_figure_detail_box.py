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


def test_conquer_detail_hides_instant_charge_but_duel_keeps_it():
    from game.components.figure_detail_box import FigureDetailBox

    figure = SimpleNamespace(get_active_skills=lambda: [
        ('instant_charge', 'Instant Advance'),
        ('distance_attack', 'Distance Attack'),
    ])
    box = FigureDetailBox.__new__(FigureDetailBox)
    box.figure = figure
    box.game = SimpleNamespace(mode='conquer')
    box.conquer_view_only = True

    assert box._active_skills_for_display() == [
        ('distance_attack', 'Distance Attack')]

    box.game.mode = 'duel'
    box.conquer_view_only = False
    assert box._active_skills_for_display() == [
        ('instant_charge', 'Instant Advance'),
        ('distance_attack', 'Distance Attack'),
    ]


def test_conquer_detail_display_copy_strips_instant_charge_description():
    from game.components.figure_detail_box import FigureDetailBox

    description = (
        'A warrior that charges instantly into battle when placed on the field. '
        'Requires food.'
    )
    family = SimpleNamespace(description=description)
    figure = SimpleNamespace(
        family=family,
        description=description,
        instant_charge=True,
        checkmate=False,
    )

    display = FigureDetailBox._display_figure_for_mode(
        figure, SimpleNamespace(mode='conquer'), conquer_view_only=True)

    assert display is not figure
    assert display.instant_charge is False
    assert 'charges instantly' not in display.description.lower()
    assert 'charges instantly' not in display.family.description.lower()
    assert figure.instant_charge is True

    duel_display = FigureDetailBox._display_figure_for_mode(
        figure, SimpleNamespace(mode='duel'))
    assert duel_display is figure
