from flask import Blueprint, request, jsonify
from sqlalchemy.orm.attributes import flag_modified
from models import db, Figure, CardToFigure, CardRole, Game, Player, MainCard, SideCard, LogEntry, User, ActiveSpell
import server_settings as settings

figures = Blueprint('figures', __name__)

def _has_active_infinite_hammer(player_id, game_id):
    """Check if player has an active Infinite Hammer spell."""
    active_hammer = ActiveSpell.query.filter_by(
        player_id=player_id,
        game_id=game_id,
        is_active=True
    ).filter(ActiveSpell.spell_name.like('%Infinite Hammer%')).first()
    return active_hammer is not None

@figures.route('/create_figure', methods=['POST'])
def create_figure():
    try:
        data = request.json
        player_id = data['player_id']
        game_id = data['game_id']
        family_name = data['family_name']
        field = data.get('field', None)
        color = data['color']
        name = data['name']
        suit = data['suit']
        description = data.get('description', "")
        upgrade_family_name = data.get('upgrade_family_name', None)
        produces = data.get('produces', {})
        requires = data.get('requires', {})
        cards = data.get('cards', [])

        if settings.DEBUG_ENABLED:
            with open(settings.DEBUG_LOG_PATH, 'a') as f:
                f.write(f"[SERVER] Creating {name}: produces={produces}, requires={requires}\n")

        if not cards:
            return jsonify({'success': False, 'message': 'No cards provided for the figure'}), 400

        # Create the figure
        figure = Figure(
            player_id=player_id,
            game_id=game_id,
            family_name=family_name,
            field=field,
            color=color,
            name=name,
            suit=suit,
            description=description,
            upgrade_family_name=upgrade_family_name,
            produces=produces,
            requires=requires
        )
        if settings.DEBUG_ENABLED:
            with open(settings.DEBUG_LOG_PATH, 'a') as f:
                f.write(f"[SERVER] Figure object created: produces={figure.produces}, requires={figure.requires}\n")
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
        
        # Check if Infinite Hammer is active for this player
        has_infinite_hammer = _has_active_infinite_hammer(player_id, game_id)
        
        if not has_infinite_hammer:
            player.turns_left -= 1
        
        db.session.commit()

        # flip turn player id only if Infinite Hammer is not active
        game = Game.query.get(game_id)
        if not has_infinite_hammer and game.turn_player_id == player_id:
            game.turn_player_id = game.players[0].id if game.players[0].id != player_id else game.players[1].id
        
        # Track action for Infinite Hammer if active
        if has_infinite_hammer:
            # Expire session to ensure we get the latest ActiveSpell data
            db.session.expire_all()
            
            from models import ActiveSpell
            active_hammer = ActiveSpell.query.filter_by(
                player_id=player_id,
                game_id=game_id,
                is_active=True
            ).filter(ActiveSpell.spell_name.like('%Infinite Hammer%')).first()
            
            if active_hammer:
                if not active_hammer.effect_data:
                    active_hammer.effect_data = {'actions': []}
                elif 'actions' not in active_hammer.effect_data:
                    active_hammer.effect_data['actions'] = []
                
                action_desc = f"built a figure with {len(cards)} cards on {field or 'field'}"
                print(f"[INFINITE_HAMMER] Tracking action: {action_desc}")
                print(f"[INFINITE_HAMMER] Current actions before append: {active_hammer.effect_data.get('actions', [])}")
                active_hammer.effect_data['actions'].append({
                    'type': 'build',
                    'description': action_desc
                })
                # Mark field as modified for SQLAlchemy
                flag_modified(active_hammer, 'effect_data')
                print(f"[INFINITE_HAMMER] Updated effect_data: {active_hammer.effect_data}")
                db.session.commit()

        # Create log entry
        user = User.query.get(player.user_id)
        username = user.username if user else f"Player {player_id}"
        card_count = len(cards)
        field_str = field if field else "their hand"
        log_entry = LogEntry(
            game_id=game_id,
            player_id=player_id,
            round_number=game.current_round,
            turn_number=player.turns_left + 1,  # +1 because we decremented it above
            message=f"{username} built a figure with {card_count} cards in {field_str}.",
            author=username,
            type='figure_built'
        )
        db.session.add(log_entry)
        db.session.commit()

        serialized = figure.serialize()
        if settings.DEBUG_ENABLED:
            with open(settings.DEBUG_LOG_PATH, 'a') as f:
                f.write(f"[SERVER] Returning serialized figure: produces={serialized.get('produces')}, requires={serialized.get('requires')}\n")
        return jsonify({'success': True, 'message': 'Figure created successfully', 'figure': serialized})

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

        # Check if Infinite Hammer is active for this player
        has_infinite_hammer = _has_active_infinite_hammer(player.id, game.id)
        
        if not has_infinite_hammer:
            player.turns_left -= 1
        
        if not has_infinite_hammer:
            game.turn_player_id = (
                game.players[0].id if game.players[0].id != player.id else game.players[1].id
            )
        
        # Track action for Infinite Hammer if active
        if has_infinite_hammer:
            # Expire session to ensure we get the latest ActiveSpell data
            db.session.expire_all()
            
            from models import ActiveSpell
            active_hammer = ActiveSpell.query.filter_by(
                player_id=player.id,
                game_id=game.id,
                is_active=True
            ).filter(ActiveSpell.spell_name.like('%Infinite Hammer%')).first()
            
            if active_hammer:
                if not active_hammer.effect_data:
                    active_hammer.effect_data = {'actions': []}
                elif 'actions' not in active_hammer.effect_data:
                    active_hammer.effect_data['actions'] = []
                
                action_desc = f"upgraded a figure to {figure.upgrade_family_name}"
                print(f"[INFINITE_HAMMER] Tracking action: {action_desc}")
                print(f"[INFINITE_HAMMER] Current actions before append: {active_hammer.effect_data.get('actions', [])}")
                active_hammer.effect_data['actions'].append({
                    'type': 'upgrade',
                    'description': action_desc
                })
                # Mark field as modified for SQLAlchemy
                flag_modified(active_hammer, 'effect_data')
                print(f"[INFINITE_HAMMER] Updated effect_data: {active_hammer.effect_data}")
                db.session.commit()

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
        print(f"[GET_FIGURES] Retrieved {len(figures)} figures for player {player_id}")
        for fig in figures:
            print(f"[GET_FIGURES] Figure: id={fig.id}, name={fig.name}, family={fig.family_name}")
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

        # Store figure field before deleting
        figure_field = figure.field if figure.field else 'field'

        # Delete the card associations and the figure itself
        CardToFigure.query.filter_by(figure_id=figure.id).delete()
        db.session.delete(figure)
        db.session.flush()

        # Update turns left for the player
        player = Player.query.get(player_id)
        
        # Check if Infinite Hammer is active for this player
        has_infinite_hammer = _has_active_infinite_hammer(player_id, game_id)
        
        if not has_infinite_hammer:
            player.turns_left -= 1
        
        db.session.commit()

        # flip turn player id only if Infinite Hammer is not active
        game = Game.query.get(game_id)
        if not has_infinite_hammer and game.turn_player_id == player_id:
            game.turn_player_id = game.players[0].id if game.players[0].id != player_id else game.players[1].id
            db.session.commit()
        
        # Track action for Infinite Hammer if active
        if has_infinite_hammer:
            # Expire session to ensure we get the latest ActiveSpell data
            db.session.expire_all()
            
            active_hammer = ActiveSpell.query.filter_by(
                player_id=player_id,
                game_id=game_id,
                is_active=True
            ).filter(ActiveSpell.spell_name.like('%Infinite Hammer%')).first()
            
            if active_hammer:
                if not active_hammer.effect_data:
                    active_hammer.effect_data = {'actions': []}
                elif 'actions' not in active_hammer.effect_data:
                    active_hammer.effect_data['actions'] = []
                
                action_desc = f"removed a figure from {figure_field}"
                print(f"[INFINITE_HAMMER] Tracking action: {action_desc}")
                print(f"[INFINITE_HAMMER] Current actions before append: {active_hammer.effect_data.get('actions', [])}")
                active_hammer.effect_data['actions'].append({
                    'type': 'delete',
                    'description': action_desc
                })
                # Mark field as modified for SQLAlchemy
                flag_modified(active_hammer, 'effect_data')
                print(f"[INFINITE_HAMMER] Updated effect_data: {active_hammer.effect_data}")
                db.session.commit()

        return jsonify({'success': True, 'message': 'Figure deleted successfully'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error deleting figure: {str(e)}'}), 400


@figures.route('/pickup_figure', methods=['POST'])
def pickup_figure():
    """Pick up a figure from the field and return its cards to the player's hand."""
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
        
        # Verify the figure belongs to the player
        if figure.player_id != player_id:
            return jsonify({'success': False, 'message': 'You can only pick up your own figures'}), 403

        # Retrieve associated cards
        card_associations = CardToFigure.query.filter_by(figure_id=figure.id).all()

        main_card_ids = []
        side_card_ids = []
        for assoc in card_associations:
            if assoc.card_type == 'main':
                main_card_ids.append(assoc.card_id)
            elif assoc.card_type == 'side':
                side_card_ids.append(assoc.card_id)

        main_cards = MainCard.query.filter(MainCard.id.in_(main_card_ids)).all()
        side_cards = SideCard.query.filter(SideCard.id.in_(side_card_ids)).all()

        # Return cards to player's hand (not to deck)
        # Cards already have player_id set, just need to set part_of_figure = False
        # and keep in_deck = False (they stay in hand)
        for card in main_cards + side_cards:
            card.part_of_figure = False
            card.in_deck = False  # Explicitly keep them in hand

        db.session.flush()

        # Delete the card associations and the figure itself
        CardToFigure.query.filter_by(figure_id=figure.id).delete()
        db.session.delete(figure)
        db.session.flush()

        # Calculate card count and field before using them
        card_count = len(main_card_ids) + len(side_card_ids)
        field_partition = figure.field if figure.field else 'field'

        # Update turns left for the player
        player = Player.query.get(player_id)
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'}), 404
        
        # Check if Infinite Hammer is active for this player
        has_infinite_hammer = _has_active_infinite_hammer(player_id, game_id)
        
        if not has_infinite_hammer:
            player.turns_left -= 1
        
        # Get game and flip turn player id only if Infinite Hammer is not active
        game = Game.query.get(game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404
        
        if not has_infinite_hammer and game.turn_player_id == player_id:
            game.turn_player_id = game.players[0].id if game.players[0].id != player_id else game.players[1].id
        
        # Track action for Infinite Hammer if active
        if has_infinite_hammer:
            # Expire session to ensure we get the latest ActiveSpell data
            db.session.expire_all()
            
            from models import ActiveSpell
            active_hammer = ActiveSpell.query.filter_by(
                player_id=player_id,
                game_id=game_id,
                is_active=True
            ).filter(ActiveSpell.spell_name.like('%Infinite Hammer%')).first()
            
            if active_hammer:
                if not active_hammer.effect_data:
                    active_hammer.effect_data = {'actions': []}
                elif 'actions' not in active_hammer.effect_data:
                    active_hammer.effect_data['actions'] = []
                
                action_desc = f"picked up a figure with {card_count} cards from {field_partition}"
                print(f"[INFINITE_HAMMER] Tracking action: {action_desc}")
                print(f"[INFINITE_HAMMER] Current actions before append: {active_hammer.effect_data.get('actions', [])}")
                active_hammer.effect_data['actions'].append({
                    'type': 'pickup',
                    'description': action_desc
                })
                # Mark field as modified for SQLAlchemy
                flag_modified(active_hammer, 'effect_data')
                print(f"[INFINITE_HAMMER] Updated effect_data: {active_hammer.effect_data}")
                db.session.commit()
        
        # Create log entry
        user = User.query.get(player.user_id)
        username = user.username if user else f"Player {player_id}"
        
        log_entry = LogEntry(
            game_id=game_id,
            player_id=player_id,
            round_number=game.current_round,
            turn_number=player.turns_left,
            message=f"{username} picked up a figure with {card_count} cards from the {field_partition}.",
            author=username,
            type='figure_pickup'
        )
        db.session.add(log_entry)

        db.session.commit()

        return jsonify({
            'success': True, 
            'message': 'Figure picked up successfully',
            'main_card_count': len(main_card_ids),
            'side_card_count': len(side_card_ids)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error picking up figure: {str(e)}'}), 400


@figures.route('/upgrade_figure', methods=['POST'])
def upgrade_figure():
    """Upgrade a figure by adding an upgrade card and changing it to a new family."""
    try:
        data = request.json
        figure_id = data.get('figure_id')
        player_id = data.get('player_id')
        game_id = data.get('game_id')
        upgrade_card_id = data.get('upgrade_card_id')
        upgrade_card_type = data.get('upgrade_card_type')  # 'main' or 'side'
        
        if not all([figure_id, player_id, game_id, upgrade_card_id, upgrade_card_type]):
            return jsonify({'success': False, 'message': 'Missing required parameters'}), 400

        # Get the figure
        figure = Figure.query.get(figure_id)
        if not figure:
            return jsonify({'success': False, 'message': 'Figure not found'}), 404
        
        # Verify the figure belongs to the player
        if figure.player_id != player_id:
            return jsonify({'success': False, 'message': 'You can only upgrade your own figures'}), 403

        # Verify the figure can be upgraded
        if not figure.upgrade_family_name:
            return jsonify({'success': False, 'message': 'This figure cannot be upgraded'}), 400

        # Verify the player owns the upgrade card
        if upgrade_card_type == 'main':
            upgrade_card = MainCard.query.get(upgrade_card_id)
        else:
            upgrade_card = SideCard.query.get(upgrade_card_id)
        
        if not upgrade_card or upgrade_card.player_id != player_id:
            return jsonify({'success': False, 'message': 'Upgrade card not found or does not belong to player'}), 403
        
        if upgrade_card.part_of_figure:
            return jsonify({'success': False, 'message': 'Upgrade card is already part of a figure'}), 400

        # Get all existing cards from the figure
        card_associations = CardToFigure.query.filter_by(figure_id=figure.id).all()
        old_cards = []
        for assoc in card_associations:
            old_cards.append({
                'id': assoc.card_id,
                'type': assoc.card_type,
                'role': assoc.role.value
            })

        # Store old figure info for log
        old_figure_name = figure.name
        new_figure_name = figure.upgrade_family_name
        figure_field = figure.field if figure.field else 'field'
        
        # Delete old figure and associations
        CardToFigure.query.filter_by(figure_id=figure.id).delete()
        db.session.delete(figure)
        db.session.flush()

        # Set part_of_figure = True for the old cards (they're going into the new figure)
        for card_info in old_cards:
            if card_info['type'] == 'main':
                card = MainCard.query.get(card_info['id'])
                if card:
                    card.part_of_figure = True
            else:
                card = SideCard.query.get(card_info['id'])
                if card:
                    card.part_of_figure = True

        # Add upgrade card to the list with 'key' role
        # (the upgrade card becomes a key card in the upgraded figure)
        old_cards.append({
            'id': upgrade_card_id,
            'type': upgrade_card_type,
            'role': 'key'
        })

        # Set upgrade card's part_of_figure = True
        upgrade_card.part_of_figure = True
        db.session.flush()

        # Create new upgraded figure
        new_figure = Figure(
            player_id=player_id,
            game_id=game_id,
            family_name=new_figure_name,
            field=figure_field,
            color=figure.color,
            name=new_figure_name,  # Use upgrade_family_name as the name
            suit=figure.suit,
            description=figure.description,
            upgrade_family_name=None  # The upgraded figure may or may not have further upgrades
        )
        db.session.add(new_figure)
        db.session.flush()

        # Add all cards (old + upgrade) to the new figure
        for card_info in old_cards:
            card_to_figure = CardToFigure(
                figure_id=new_figure.id,
                card_id=card_info['id'],
                card_type=card_info['type'],
                role=CardRole(card_info['role'])
            )
            db.session.add(card_to_figure)

        db.session.flush()

        # Serialize the new figure BEFORE expiring session for Infinite Hammer tracking
        new_figure_serialized = new_figure.serialize()
        print(f"[UPGRADE_FIGURE] Created new figure: id={new_figure.id}, name={new_figure_name}, player_id={player_id}")
        print(f"[UPGRADE_FIGURE] Serialized: {new_figure_serialized}")

        # Update turns left for the player
        player = Player.query.get(player_id)
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'}), 404
        
        # Check if Infinite Hammer is active for this player
        has_infinite_hammer = _has_active_infinite_hammer(player_id, game_id)
        
        if not has_infinite_hammer:
            player.turns_left -= 1
        
        # Get game and flip turn player id only if Infinite Hammer is not active
        game = Game.query.get(game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404
        
        if not has_infinite_hammer and game.turn_player_id == player_id:
            game.turn_player_id = game.players[0].id if game.players[0].id != player_id else game.players[1].id
        
        # Create log entry BEFORE Infinite Hammer tracking
        user = User.query.get(player.user_id)
        username = user.username if user else f"Player {player_id}"
        
        log_entry = LogEntry(
            game_id=game_id,
            player_id=player_id,
            round_number=game.current_round,
            turn_number=player.turns_left,
            message=f"{username} upgraded a {figure_field} {old_figure_name} to {new_figure_name}.",
            author=username,
            type='figure_upgraded'
        )
        db.session.add(log_entry)
        
        # Commit everything BEFORE Infinite Hammer tracking to ensure new figure is in DB
        db.session.commit()
        print(f"[UPGRADE_FIGURE] Committed new figure and log entry")
        
        # Track action for Infinite Hammer if active
        if has_infinite_hammer:
            # Expire session to ensure we get the latest ActiveSpell data
            db.session.expire_all()
            
            from models import ActiveSpell
            active_hammer = ActiveSpell.query.filter_by(
                player_id=player_id,
                game_id=game_id,
                is_active=True
            ).filter(ActiveSpell.spell_name.like('%Infinite Hammer%')).first()
            
            if active_hammer:
                if not active_hammer.effect_data:
                    active_hammer.effect_data = {'actions': []}
                elif 'actions' not in active_hammer.effect_data:
                    active_hammer.effect_data['actions'] = []
                
                action_desc = f"upgraded a {figure_field} {old_figure_name} to {new_figure_name}"
                print(f"[INFINITE_HAMMER] Tracking action: {action_desc}")
                print(f"[INFINITE_HAMMER] Current actions before append: {active_hammer.effect_data.get('actions', [])}")
                active_hammer.effect_data['actions'].append({
                    'type': 'upgrade',
                    'description': action_desc
                })
                # Mark field as modified for SQLAlchemy
                flag_modified(active_hammer, 'effect_data')
                print(f"[INFINITE_HAMMER] Updated effect_data: {active_hammer.effect_data}")
                db.session.commit()
                print(f"[INFINITE_HAMMER] Committed action tracking")

        return jsonify({
            'success': True,
            'message': 'Figure upgraded successfully',
            'new_figure': new_figure_serialized
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error upgrading figure: {str(e)}'}), 400
