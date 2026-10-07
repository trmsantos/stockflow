"""Entrypoint WSGI (gunicorn).

O default é `prod`: num contentor sem `DJANGO_SETTINGS_MODULE` definido é
preferível falhar por falta de variáveis de ambiente do que servir em silêncio
com as settings de desenvolvimento.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_wsgi_application()
