# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.

import os

# Server and database configurations
SERVER_URL = os.getenv(
    'SERVER_URL',
    'https://api-nepalkingz.eu.pythonanywhere.com',
)
DB_URL = os.getenv('DB_URL', 'sqlite:///test.db')

# Debug logging
DEBUG_ENABLED = os.getenv('DEBUG_ENABLED', 'False').lower() == 'true'
DEBUG_LOG_PATH = os.getenv('DEBUG_LOG_PATH', '/tmp/nepalkings_debug.log')
