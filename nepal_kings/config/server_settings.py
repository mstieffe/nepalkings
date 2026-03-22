
import os

# Server and database configurations
SERVER_URL = os.getenv('SERVER_URL', 'https://nepalkings.pythonanywhere.com')
DB_URL = os.getenv('DB_URL', 'sqlite:///test.db')

# Debug logging
DEBUG_ENABLED = os.getenv('DEBUG_ENABLED', 'False').lower() == 'true'
DEBUG_LOG_PATH = os.getenv('DEBUG_LOG_PATH', '/tmp/nepalkings_debug.log')

