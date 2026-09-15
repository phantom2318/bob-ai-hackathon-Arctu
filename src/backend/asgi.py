"""
ASGI config for Weatheria project.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')

from django.core.asgi import get_asgi_application

application = get_asgi_application()
