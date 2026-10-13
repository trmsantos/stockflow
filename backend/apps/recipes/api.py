"""A porta do módulo `recipes` (ARCHITECTURE.md §3).

Fatia 6: produção de receitas.

Expõe DTOs (frozen dataclasses) e funções que outros módulos chamam via api.py.
Nenhuma escrita direta: tudo via services.py.
"""

from __future__ import annotations

from apps.recipes.services import produzir

__all__ = [
    "produzir",
]
