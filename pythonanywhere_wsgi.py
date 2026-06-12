# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import sys
import os

path = '/home/nepalkings/nepalkings/server'
if path not in sys.path:
    sys.path.insert(0, path)

# Production deployment: set a fixed SECRET_KEY in this private WSGI file
# before importing the app. Do not commit a real key to the repo.
# Example:
# os.environ['SECRET_KEY'] = 'paste-a-64-char-random-hex-string-here'
os.environ['FLASK_ENV'] = 'production'
os.environ['DROP_TABLES_ON_STARTUP'] = 'False'
os.environ['DB_URL'] = f'sqlite:///{path}/instance/nepalkings.db'
os.environ['SERVER_URL'] = 'https://nepalkings.pythonanywhere.com'

# If the web client is hosted on GitHub Pages (or any origin other than the
# API origin), list that origin here so the browser may call the API.
# Examples:
# os.environ['CORS_ORIGINS'] = 'https://YOURNAME.github.io'
# os.environ['CORS_ORIGINS'] = 'https://YOURNAME.github.io,https://www.example.com'

# AI Opponent (rule-based, no external API).
os.environ['AI_ENABLED'] = 'True'

from wsgi import application
