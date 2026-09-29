"""Entrypoint ASGI (uvicorn). Ver a nota sobre o default em `config/wsgi.py`."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_asgi_application()
