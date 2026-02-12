"""
Utility functions for server operations.
"""
from models import db, MainCard, SideCard, LogEntry
from server.game_service.deck_manager import DeckManager
import server_settings


def check_and_fill_minimum_cards(game, player):
    """
    Check if player has minimum required cards and automatically fill up if needed.
    
    :param game: Game instance
    :param player: Player instance
    :return: Dictionary with fill information
    """
    fill_info = {
        'filled': False,
        'main_cards_drawn': 0,
        'side_cards_drawn': 0,
        'drawn_cards': []
    }
    
    # Count current cards
    main_count = MainCard.query.filter_by(
        player_id=player.id,
        in_deck=False,
        part_of_figure=False
    ).count()
    
    side_count = SideCard.query.filter_by(
        player_id=player.id,
        in_deck=False,
        part_of_figure=False
    ).count()
    
    # Check and fill main cards
    if main_count < server_settings.NUM_MIN_MAIN_CARDS:
        cards_needed = server_settings.NUM_MIN_MAIN_CARDS - main_count
        try:
            drawn_main = DeckManager.draw_cards_from_deck(game, player, cards_needed, 'main')
            fill_info['filled'] = True
            fill_info['main_cards_drawn'] = len(drawn_main)
            for card in drawn_main:
                card_data = card.serialize()
                card_data['type'] = 'main'
                fill_info['drawn_cards'].append(card_data)
        except Exception as e:
            print(f"Could not fill main cards: {e}")
    
    # Check and fill side cards
    if side_count < server_settings.NUM_MIN_SIDE_CARDS:
        cards_needed = server_settings.NUM_MIN_SIDE_CARDS - side_count
        try:
            drawn_side = DeckManager.draw_cards_from_deck(game, player, cards_needed, 'side')
            fill_info['filled'] = True
            fill_info['side_cards_drawn'] = len(drawn_side)
            for card in drawn_side:
                card_data = card.serialize()
                card_data['type'] = 'side'
                fill_info['drawn_cards'].append(card_data)
        except Exception as e:
            print(f"Could not fill side cards: {e}")
    
    # Add log entry if cards were auto-filled
    if fill_info['filled']:
        log_parts = []
        if fill_info['main_cards_drawn'] > 0:
            log_parts.append(f"{fill_info['main_cards_drawn']} main card{'s' if fill_info['main_cards_drawn'] > 1 else ''}")
        if fill_info['side_cards_drawn'] > 0:
            log_parts.append(f"{fill_info['side_cards_drawn']} side card{'s' if fill_info['side_cards_drawn'] > 1 else ''}")
        
        log_message = f"{player.serialize()['username']} auto-filled {' and '.join(log_parts)} to reach minimum"
        add_log_entry(
            game.id, player.id, game.current_round,
            player.turns_left, 'Auto-Fill', 'auto_fill',
            log_message
        )
    
    return fill_info


def add_log_entry(game_id, player_id, round_num, turn_num, action, log_type, message):
    """
    Add a log entry to the game.
    
    :param game_id: Game ID
    :param player_id: Player ID
    :param round_num: Current round number
    :param turn_num: Current turn number
    :param action: Action name (for reference, not stored directly)
    :param log_type: Type of log entry
    :param message: Log message
    """
    log_entry = LogEntry(
        game_id=game_id,
        player_id=player_id,
        round_number=round_num,
        turn_number=turn_num,
        message=message,
        author='system',
        type=log_type
    )
    db.session.add(log_entry)
    db.session.commit()
