from typing import List, Dict
from game.components.figures.figure import Figure, FigureFamily
from game.components.cards.card import Card
from utils.figure_service import (
    fetch_figures,
    fetch_figure,
    create_figure,
    update_figure,
    delete_figure,
)
from config import settings


class FigureDbService:
    @staticmethod
    def load_figures(player_id: int, families: Dict[str, FigureFamily]) -> List[Figure]:
        """
        Load all figures for a specific player from the database and convert them into Figure instances.

        :param player_id: ID of the player.
        :param families: A dictionary of FigureFamily instances keyed by family name.
        :return: A list of Figure instances.
        """
        figures_data = fetch_figures(player_id)
        figures = []
        for figure_data in figures_data:
            family_name = figure_data['family_name']
            if family_name not in families:
                raise ValueError(f"Unknown family name: {family_name}")

            family = families[family_name]
            cards = FigureDbService._load_cards_from_data(figure_data['cards'])
            figure = FigureDbService._create_figure_instance(figure_data, family, cards)

            figures.append(figure)

        return figures

    @staticmethod
    def load_figure(figure_id: int, families: Dict[str, FigureFamily]) -> Figure:
        """
        Load a single figure by its ID from the database.

        :param figure_id: ID of the figure.
        :param families: A dictionary of FigureFamily instances keyed by family name.
        :return: A Figure instance.
        """
        figure_data = fetch_figure(figure_id)
        family_name = figure_data['family_name']

        if family_name not in families:
            raise ValueError(f"Unknown family name: {family_name}")

        family = families[family_name]
        cards = FigureDbService._load_cards_from_data(figure_data['cards'])
        return FigureDbService._create_figure_instance(figure_data, family, cards)

    @staticmethod
    def save_figure(figure: Figure, player_id: int, game_id: int) -> Dict:
        """
        Save a figure to the server.

        :param figure: The Figure object.
        :param player_id: Player ID.
        :param game_id: Game ID.
        """
        # Prepare card-role mapping
        serialized_cards = [
            {
                "id": card.id,
                "type": "main" if card.is_main_card else "side",
                "role": "key" if card in figure.key_cards else
                        ("number" if card == figure.number_card else
                        "upgrade" if card == figure.upgrade_card else None)
            }
            for card in figure.cards
        ]

        # Extract fields from the figure
        family_name = figure.family.name
        color = figure.family.color
        name = figure.name
        suit = figure.suit
        description = figure.description
        upgrade_family_name = figure.upgrade_family_name

        # Call create_figure with individual arguments
        return create_figure(
            player_id=player_id,
            game_id=game_id,
            family_name=family_name,
            color=color,
            name=name,
            suit=suit,
            description=description,
            upgrade_family_name=upgrade_family_name,
            cards=serialized_cards
        )

    @staticmethod
    def update_figure(figure: Figure) -> Dict:
        """
        Update a Figure instance in the database.

        :param figure: The Figure instance to update.
        :return: The response from the server.
        """
        serialized_cards = [
            {
                'id': card.id,
                'type': 'main' if card.is_main_card else 'side',
                'role': 'key' if card in figure.key_cards else
                        'number' if card == figure.number_card else
                        'upgrade' if card == figure.upgrade_card else None
            }
            for card in figure.cards if card.id
        ]

        return update_figure(
            figure_id=figure.id,
            name=figure.name,
            suit=figure.suit,
            description=figure.description,
            upgrade_family_name=figure.upgrade_family_name,
            cards=serialized_cards,
        )

    @staticmethod
    def delete_figure(figure_id: int) -> Dict:
        """
        Delete a Figure instance from the database.

        :param figure_id: The ID of the figure to delete.
        :return: The response from the server.
        """
        return delete_figure(figure_id)

    @staticmethod
    def _create_figure_instance(
        figure_data: Dict, family: FigureFamily, cards: Dict[str, List[Card]]
    ) -> Figure:
        """
        Create a Figure instance from database data.

        :param figure_data: The dictionary of figure data from the database.
        :param family: The FigureFamily instance associated with the figure.
        :param cards: A dictionary of cards categorized by their roles.
        :return: A Figure instance.
        """
        try:

            # Validate cards
            if not any(cards.values()):
                raise ValueError(f"Figure '{figure_data['name']}' has no valid cards.")

            # Safely extract cards
            key_cards = cards.get('key', [])
            number_card = cards.get('number', [None])[0] if cards.get('number') else None
            upgrade_card = cards.get('upgrade', [None])[0] if cards.get('upgrade') else None

            # Create the figure
            figure = Figure(
                name=figure_data['name'],
                sub_name=figure_data.get('sub_name', ""),
                suit=figure_data['suit'],
                family=family,
                key_cards=key_cards,
                number_card=number_card,
                upgrade_card=upgrade_card,
                description=figure_data.get('description', ""),
                upgrade_family_name=figure_data.get('upgrade_family_name'),
                id=figure_data['id'],
            )

            return figure

        except Exception as e:
            print(f"Error in _create_figure_instance: {e}")
            raise



    @staticmethod
    def _load_cards_from_data(cards_data: List[Dict]) -> Dict[str, List[Card]]:
        """
        Convert card data from the database into Card instances grouped by role.

        :param cards_data: A list of card data dictionaries from the database.
        :return: A dictionary with card roles as keys and lists of Card instances as values.
        """
        cards = {'key': [], 'number': [], 'upgrade': []}

        for card_data in cards_data:
            try:
                card = Card(
                    rank=card_data['rank'],
                    suit=card_data['suit'],
                    value=card_data['value'],
                    id=card_data['card_id'],  # Use `card_id` as `id`
                    game_id=card_data.get('game_id'),
                    player_id=card_data.get('player_id'),
                    in_deck=card_data.get('in_deck'),
                    deck_position=card_data.get('deck_position'),
                    part_of_figure=card_data.get('part_of_figure'),
                    type=card_data.get('card_type'),
                    role=card_data.get('role')
                )
                cards[card.role].append(card)
            except KeyError as e:
                print(f"KeyError: Missing field in card data {card_data}. Error: {e}")
                continue

        # Ensure at least one card is present
        if not any(cards.values()):
            raise ValueError("No valid cards provided for this figure.")

        return cards

