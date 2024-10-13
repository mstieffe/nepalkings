from game_service.models import db, Game, Player, Card

def create_deck(game):
    ranks = ['02', '03', '04', '05', '06', '07', '08', '09', '10', 'J', 'Q', 'K', 'A']
    suits = ['H', 'D', 'C', 'S']  # Hearts, Diamonds, Clubs, Spades

    cards = []

    for suit in suits:
        for rank in ranks:
            card = Card(game_id=game.id, rank=rank, suit=suit)
            cards.append(card)
            db.session.add(card)
    game.cards = cards
    db.session.commit()


def deal_cards(game):
    players = game.players
    cards = game.cards

    for i, card in enumerate(cards):
        card.player_id = players[i % len(players)].id

    db.session.commit()

def start_game():
    game = Game()
    player1 = Player(game=game)
    player2 = Player(game=game)

    db.session.add(game)
    db.session.add(player1)
    db.session.add(player2)
    db.session.commit()

    create_deck(game)
    deal_cards(game)

    game.current_player_id = player1.id
    db.session.commit()