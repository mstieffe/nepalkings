from flask import Blueprint, request, jsonify
from models import db, Figure, CardToFigure, CardRole, Game, Player, MainCard, SideCard

figures = Blueprint('figures', __name__)

@figures.route('/create_figure', methods=['POST'])
def create_figure():
    try:
        data = request.json
        player_id = data['player_id']
        game_id = data['game_id']
        family_name = data['family_name']
        color = data['color']
        name = data['name']
        suit = data['suit']
        description = data.get('description', "")
        upgrade_family_name = data.get('upgrade_family_name', None)
        cards = data.get('cards', [])

        if not cards:
            return jsonify({'success': False, 'message': 'No cards provided for the figure'}), 400

        # Create the figure
        figure = Figure(
            player_id=player_id,
            game_id=game_id,
            family_name=family_name,
            color=color,
            name=name,
            suit=suit,
            description=description,
            upgrade_family_name=upgrade_family_name
        )
        db.session.add(figure)
        db.session.flush()  # Flush to get figure.id before committing

        # Add cards to the figure and update card attributes
        for card in cards:
            card_to_figure = CardToFigure(
                figure_id=figure.id,
                card_id=card['id'],
                card_type=card['type'],
                role=CardRole(card['role'])
            )
            db.session.add(card_to_figure)

            # Update card's part_of_figure attribute
            if card['type'] == 'main':
                main_card = MainCard.query.get(card['id'])
                if main_card:
                    main_card.part_of_figure = True
            elif card['type'] == 'side':
                side_card = SideCard.query.get(card['id'])
                if side_card:
                    side_card.part_of_figure = True

        db.session.flush()

        # Update turns left for the player
        player = Player.query.get(player_id)
        player.turns_left -= 1
        db.session.commit()

        # flip turn player id
        game = Game.query.get(game_id)
        if game.turn_player_id == player_id:
            game.turn_player_id = game.players[0].id if game.players[0].id != player_id else game.players[1].id
            db.session.commit()

        return jsonify({'success': True, 'message': 'Figure created successfully', 'figure': figure.serialize()})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error creating figure: {str(e)}'}), 400


@figures.route('/update_figure', methods=['POST'])
def update_figure():
    try:
        data = request.json
        figure_id = data['figure_id']
        if not figure_id:
            return jsonify({'success': False, 'message': 'Figure ID is required'}), 400

        figure = Figure.query.get(figure_id)
        if not figure:
            return jsonify({'success': False, 'message': 'Figure not found'}), 404

        # Update figure fields
        figure.name = data.get('name', figure.name)
        figure.suit = data.get('suit', figure.suit)
        figure.description = data.get('description', figure.description)
        figure.upgrade_family_name = data.get('upgrade_family_name', figure.upgrade_family_name)

        # Update card associations
        if 'cards' in data:
            # Clear existing card associations
            CardToFigure.query.filter_by(figure_id=figure.id).delete()

            # Add new associations
            for card in data['cards']:
                card_to_figure = CardToFigure(
                    figure_id=figure.id,
                    card_id=card['id'],
                    card_type=card['type'],
                    role=CardRole(card['role'])
                )
                db.session.add(card_to_figure)

        db.session.commit()

        # Update turns left and flip turn player
        player = Player.query.get(figure.player_id)
        game = Game.query.get(figure.game_id)
        if not player or not game:
            return jsonify({'success': False, 'message': 'Player or game not found'}), 404

        player.turns_left -= 1
        game.turn_player_id = (
            game.players[0].id if game.players[0].id != player.id else game.players[1].id
        )

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Figure updated successfully',
            'figure': figure.serialize(),
            'turns_left': player.turns_left
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error updating figure: {str(e)}'}), 400


@figures.route('/get_figure', methods=['GET'])
def get_figure():
    try:
        figure_id = request.args.get('figure_id')
        if not figure_id:
            return jsonify({'success': False, 'message': 'Figure ID is required'}), 400

        figure = Figure.query.get(figure_id)
        if not figure:
            return jsonify({'success': False, 'message': 'Figure not found'}), 404

        return jsonify({'success': True, 'figure': figure.serialize()})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error retrieving figure: {str(e)}'}), 400


@figures.route('/get_figures', methods=['GET'])
def get_figures():
    try:
        player_id = request.args.get('player_id')
        if not player_id:
            return jsonify({'success': False, 'message': 'Player ID is required'}), 400

        figures = Figure.query.filter_by(player_id=player_id).all()
        return jsonify({'success': True, 'figures': [figure.serialize() for figure in figures]})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error retrieving figures: {str(e)}'}), 400



@figures.route('/delete_figure', methods=['POST'])
def delete_figure():
    try:
        data = request.json
        figure_id = data.get('figure_id')
        player_id = data.get('player_id')
        game_id = data.get('game_id')
        
        if not figure_id:
            return jsonify({'success': False, 'message': 'Figure ID is required'}), 400

        figure = Figure.query.get(figure_id)
        if not figure:
            return jsonify({'success': False, 'message': 'Figure not found'}), 404

        # Retrieve associated cards
        card_associations = CardToFigure.query.filter_by(figure_id=figure.id).all()
        card_ids = [assoc.card_id for assoc in card_associations]

        main_card_ids = []
        side_card_ids = []
        for assoc in card_associations:
            if assoc.card_type == 'main':
                main_card_ids.append(assoc.card_id)
            elif assoc.card_type == 'side':
                side_card_ids.append(assoc.card_id)

        main_cards = MainCard.query.filter(MainCard.id.in_(main_card_ids)).all()
        side_cards = SideCard.query.filter(SideCard.id.in_(side_card_ids)).all()

        # Return cards to the deck and update card attributes
        from game_service.deck import DeckManager
        DeckManager.return_cards_to_deck(main_cards)
        DeckManager.return_cards_to_deck(side_cards)

        for card in main_cards + side_cards:
            card.part_of_figure = False

        db.session.flush()

        # Delete the card associations and the figure itself
        CardToFigure.query.filter_by(figure_id=figure.id).delete()
        db.session.delete(figure)
        db.session.flush()

        # Update turns left for the player
        player = Player.query.get(player_id)
        player.turns_left -= 1
        db.session.commit()

        # flip turn player id
        game = Game.query.get(game_id)
        if game.turn_player_id == player_id:
            game.turn_player_id = game.players[0].id if game.players[0].id != player_id else game.players[1].id
            db.session.commit()

        return jsonify({'success': True, 'message': 'Figure deleted successfully'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error deleting figure: {str(e)}'}), 400
