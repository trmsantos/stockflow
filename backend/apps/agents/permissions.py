"""A permissão que falta ao `PertenceAoTenant`: a conversa é **da pessoa**.

`has_object_permission` compara o tenant **e** o autor (ADR 0027, decisão 2), e
a recusa é 404 e não 403: um 403 confirmaria a quem não é autor que a conversa
existe. Levanta `Http404` em vez de devolver `False` porque o DRF transforma um
`False` em 403, e o que se quer aqui é a mesma resposta que o `get_queryset`
filtrado por `created_by` já dá — esta classe é a segunda rede, para o caso de
uma queryset construída fora do filtro.
"""

from __future__ import annotations

from typing import Any

from django.http import Http404, HttpRequest
from rest_framework.permissions import BasePermission
from rest_framework.views import APIView

__all__ = ["EAutorDaConversa"]


class EAutorDaConversa(BasePermission):
    """O objecto é uma conversa deste tenant criada por quem pede. Senão, 404."""

    def has_permission(self, request: HttpRequest, view: APIView) -> bool:
        return True

    def has_object_permission(self, request: HttpRequest, view: APIView, obj: Any) -> bool:
        contexto = getattr(request, "tenant", None)
        utilizador = getattr(request, "user", None)
        tenant_do_objeto = getattr(obj, "tenant_id", None)
        autor = getattr(obj, "created_by_id", None)
        if (
            contexto is None
            or utilizador is None
            or tenant_do_objeto != contexto.id
            or autor is None
            or autor != utilizador.pk
        ):
            raise Http404
        return True
