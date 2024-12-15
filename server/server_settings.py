
import os

# Server and database configurations
SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:5000')
DB_URL = os.getenv('DB_URL', 'sqlite:///test.db')

# Game Logic
NUM_MAIN_CARDS_START = 12
NUM_SIDE_CARDS_START = 4

INITIAL_TURNS = 4
