
import os

# Server and database configurations
SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:5000')
DB_URL = os.getenv('DB_URL', 'sqlite:///test.db')
