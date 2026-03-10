"""WSGI entry point for PythonAnywhere (or any WSGI host).

In PythonAnywhere's Web tab, set the WSGI configuration file to point here:

    import sys
    sys.path.insert(0, '/home/YOUR_USERNAME/nepalkings/server')
    from wsgi import application
"""

import os
import sys

# Ensure the server directory is on the path
_dir = os.path.dirname(os.path.abspath(__file__))
if _dir not in sys.path:
    sys.path.insert(0, _dir)

# Production defaults — override via PythonAnywhere environment variables
os.environ.setdefault('DROP_TABLES_ON_STARTUP', 'False')
os.environ.setdefault('DB_URL', f'sqlite:///{os.path.join(_dir, "instance", "nepalkings.db")}')

from server import app as application  # noqa: E402
