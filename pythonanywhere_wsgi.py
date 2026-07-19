# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import os
import sys

path = '/home/nepalkingz/nepalkings/server'
env_file = '/home/nepalkingz/.config/nepalkings/production.env'
if path not in sys.path:
    sys.path.insert(0, path)

# The committed wrapper contains no secrets. server/wsgi.py loads this private
# chmod-600 file before importing application settings.
os.environ['NEPAL_KINGS_ENV_FILE'] = env_file

from wsgi import application  # noqa: E402,F401
