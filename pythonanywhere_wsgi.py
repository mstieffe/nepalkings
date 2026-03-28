# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import sys
import os

path = '/home/nepalkings/nepalkings/server'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['DROP_TABLES_ON_STARTUP'] = 'False'
os.environ['DB_URL'] = f'sqlite:///{path}/instance/nepalkings.db'
os.environ['SERVER_URL'] = 'https://nepalkings.pythonanywhere.com'

from wsgi import application
