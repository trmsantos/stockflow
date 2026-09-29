#!/usr/bin/env python
"""Utilitário de linha de comandos do Django para o StockFlow."""

import os
import sys


def main() -> None:
    """Corre as tarefas administrativas do Django."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - ambiente mal configurado
        raise ImportError(
            "Não foi possível importar o Django. Confirma que está instalado e "
            "disponível na PYTHONPATH. Corre `uv sync` e usa `uv run manage.py`."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
