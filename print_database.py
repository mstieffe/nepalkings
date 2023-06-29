from flask import Flask
from models import db, User, Game, Player, Card
import settings

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = settings.DB_URL
db.init_app(app)

with app.app_context():
    users = User.query.all()
    games = Game.query.all()
    players = Player.query.all()
    cards = Card.query.all()

    print("########### USER #############")
    user_columns = User.__table__.columns.keys()
    for user in users:
        user_info = ', '.join(f'{column}: {getattr(user, column)}' for column in user_columns)
        print(user_info)

    print("########### GAME #############")
    game_columns = Game.__table__.columns.keys()
    for game in games:
        game_info = ', '.join(f'{column}: {getattr(game, column)}' for column in game_columns)
        print(game_info)

    print("########### PLAYER #############")
    player_columns = Player.__table__.columns.keys()
    for player in players:
        player_info = ', '.join(f'{column}: {getattr(player, column)}' for column in player_columns)
        print(player_info)

    print("########### CARD #############")
    card_columns = Card.__table__.columns.keys()
    for card in cards:
        card_info = ', '.join(f'{column}: {getattr(card, column)}' for column in card_columns)
        print(card_info)
