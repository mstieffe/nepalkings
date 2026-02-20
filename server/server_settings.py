
import os

# Server and database configurations
SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:5000')
DB_URL = os.getenv('DB_URL', 'sqlite:///test.db')

# Database management
# Set to True to drop and recreate all tables on server startup (useful for schema changes)
# WARNING: This will delete all data! Set to False for production.
DROP_TABLES_ON_STARTUP = os.getenv('DROP_TABLES_ON_STARTUP', 'False').lower() == 'true'

# Debug logging
DEBUG_ENABLED = os.getenv('DEBUG_ENABLED', 'False').lower() == 'true'
DEBUG_LOG_PATH = os.getenv('DEBUG_LOG_PATH', '/tmp/nepalkings_debug.log')

# Game Logic
NUM_MAIN_CARDS_START = 5
NUM_SIDE_CARDS_START = 8

NUM_MIN_MAIN_CARDS = 5
NUM_MIN_SIDE_CARDS = 0

INITIAL_TURNS = 4



