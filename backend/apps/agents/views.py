"""O contrato HTTP do assistente: `/api/v1/assistant/conversations` (ADR 0027, decisão 4).

Cinco operações e nenhum endpoint só para polling: o `POST` responde **202 com a
mensagem** e o cliente sonda o `GET` da conversa a 2 s, como o `/documents`
(ADR 0020, decisão 3). As recusas saem com `code` e com o texto traduzido.

| Método e caminho | Resposta |
|---|---|
| `POST /assistant/conversations {question}` | 202 `ConversaOut` — cria **e** pergunta |
| `GET  /assistant/conversations` | 200 lista paginada, só as minhas |
| `GET  /assistant/conversations/<id>` | 200 `ConversaOut` com os turnos |
| `POST /assistant/conversations/<id>/messages {question}` | 202 `MensagemOut` |
| `DELETE /assistant/conversations/<id>` | 204 |

`IsAuthenticated + PertenceAoTenant` em tudo; o autor é verificado nas que
recebem `pk` pelo `get_queryset` (404) e pela `EAutorDaConversa` (também 404).
`ScopedRateThrottle` `assistente` nas escritas.
"""

from __future__ import annotations

from django.conf import settings
from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle

from apps.accounts.api import PertenceAoTenant, membership_atual
from apps.agents.models import Conversation
from apps.agents.permissions import EAutorDaConversa
from apps.agents.selectors import conversa_do_utilizador, conversas_do_utilizador
from apps.agents.serializers import (
    ConversaOutSerializer,
    ConversaResumoOutSerializer,
    MensagemOutSerializer,
    PerguntaInSerializer,
    RecusaDoAssistenteOutSerializer,
)
from apps.agents.services import (
    ASSISTENTE_INDISPONIVEL,
    CONVERSA_CHEIA,
    RESPOSTA_PENDENTE,
    TETO_DIARIO_ATINGIDO,
    RecusaDoAssistente,
    apagar_conversa,
    criar_conversa,
    fazer_pergunta,
)

__all__ = ["STATUS_DA_RECUSA", "ConversaViewSet"]

#: O balde do throttle das escritas (`DEFAULT_THROTTLE_RATES`, 10/min).
AMBITO_THROTTLE = "assistente"

#: O status HTTP de cada código de recusa. Um código fora do mapa seria um
#: `KeyError` e portanto um 500 — é por isso que não há default aqui.
STATUS_DA_RECUSA: dict[str, int] = {
    ASSISTENTE_INDISPONIVEL: status.HTTP_503_SERVICE_UNAVAILABLE,
    TETO_DIARIO_ATINGIDO: status.HTTP_429_TOO_MANY_REQUESTS,
    RESPOSTA_PENDENTE: status.HTTP_409_CONFLICT,
    CONVERSA_CHEIA: status.HTTP_409_CONFLICT,
}

_RECUSAS = {
    status.HTTP_409_CONFLICT: RecusaDoAssistenteOutSerializer,
    status.HTTP_429_TOO_MANY_REQUESTS: RecusaDoAssistenteOutSerializer,
    status.HTTP_503_SERVICE_UNAVAILABLE: RecusaDoAssistenteOutSerializer,
}


@extend_schema_view(
    list=extend_schema(
        operation_id="assistente_conversas_listar",
        summary="As conversas de quem pede, mais recentes primeiro",
        responses={status.HTTP_200_OK: ConversaResumoOutSerializer(many=True)},
    ),
    retrieve=extend_schema(
        operation_id="assistente_conversa",
        summary="Uma conversa com os turnos — o alvo do polling",
        responses={status.HTTP_200_OK: ConversaOutSerializer},
    ),
    create=extend_schema(
        operation_id="assistente_perguntar",
        summary="Abrir uma conversa com a primeira pergunta",
        description=(
            "Cria a conversa **e** faz a primeira pergunta: não existe conversa vazia. "
            "Responde 202 com a conversa e o turno `pendente`; a resposta chega por "
            "polling do `GET` da conversa. 503 `assistente_indisponivel` sem modelo ou "
            "chave; 429 `teto_diario_atingido` nos dois tetos diários."
        ),
        request=PerguntaInSerializer,
        responses={status.HTTP_202_ACCEPTED: ConversaOutSerializer, **_RECUSAS},
    ),
    destroy=extend_schema(
        operation_id="assistente_conversa_apagar",
        summary="Apagar uma conversa minha",
        responses={status.HTTP_204_NO_CONTENT: None},
    ),
    messages=extend_schema(
        operation_id="assistente_perguntar_na_conversa",
        summary="A pergunta seguinte numa conversa",
        description=(
            "202 com o turno `pendente`. 409 `resposta_pendente` enquanto o turno "
            "anterior não acabar; 409 `conversa_cheia` ao trigésimo turno."
        ),
        request=PerguntaInSerializer,
        responses={status.HTTP_202_ACCEPTED: MensagemOutSerializer, **_RECUSAS},
    ),
)
class ConversaViewSet(viewsets.GenericViewSet):
    """As conversas de uma pessoa com o assistente, num estabelecimento."""

    permission_classes = [IsAuthenticated, PertenceAoTenant, EAutorDaConversa]
    serializer_class = ConversaOutSerializer
    # `none()` ao nível da classe pela razão do `RececaoViewSet`: é daqui que o
    # drf-spectacular deriva o tipo do `pk`; o `get_queryset` sobrepõe-se.
    queryset = Conversation.objects.none()
    throttle_scope = AMBITO_THROTTLE

    def get_throttles(self) -> list[BaseThrottle]:
        """O balde `assistente` só nas escritas; as leituras ficam no do utilizador."""
        if self.request.method in SAFE_METHODS:
            return super().get_throttles()
        return [*super().get_throttles(), ScopedRateThrottle()]

    def get_queryset(self) -> QuerySet[Conversation]:
        """Só as conversas de quem pede, neste estabelecimento: a de outro é 404."""
        return conversas_do_utilizador(
            tenant_id=self.request.tenant.id, user_id=self.request.user.pk
        )

    def list(self, request: Request) -> Response:
        pagina = self.paginate_queryset(self.get_queryset())
        dados = ConversaResumoOutSerializer(pagina, many=True).data
        return self.get_paginated_response(dados)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        conversa = self.get_object()
        return Response(self._conversa_completa(conversa))

    def create(self, request: Request) -> Response:
        entrada = PerguntaInSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            conversa = criar_conversa(
                tenant_id=request.tenant.id,
                autor=membership_atual(request),
                pergunta=entrada.validated_data["question"],
                lingua=_lingua(request),
                request_id=getattr(request, "request_id", None),
            )
        except RecusaDoAssistente as recusa:
            return _resposta_de_recusa(recusa)
        return Response(self._conversa_completa(conversa), status=status.HTTP_202_ACCEPTED)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        apagar_conversa(conversa=self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="messages", url_name="mensagens")
    def messages(self, request: Request, pk: str | None = None) -> Response:
        conversa = self.get_object()
        entrada = PerguntaInSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            mensagem = fazer_pergunta(
                tenant_id=request.tenant.id,
                conversa=conversa,
                autor=membership_atual(request),
                pergunta=entrada.validated_data["question"],
                lingua=_lingua(request),
                request_id=getattr(request, "request_id", None),
            )
        except RecusaDoAssistente as recusa:
            return _resposta_de_recusa(recusa)
        return Response(MensagemOutSerializer(mensagem).data, status=status.HTTP_202_ACCEPTED)

    def _conversa_completa(self, conversa: Conversation) -> dict:
        """O `ConversaOut` recarregado com os turnos, em duas queries."""
        completa = conversa_do_utilizador(
            tenant_id=self.request.tenant.id,
            user_id=self.request.user.pk,
            conversa_id=conversa.pk,
        )
        return ConversaOutSerializer(completa if completa is not None else conversa).data


def _lingua(request: Request) -> str:
    """O `LANGUAGE_CODE` que o `LocaleMiddleware` activou; é o que o turno guarda."""
    codigo = str(getattr(request, "LANGUAGE_CODE", "") or "").lower()
    linguas = {lingua for lingua, _nome in settings.LANGUAGES}
    return codigo if codigo in linguas else settings.LANGUAGE_CODE


def _resposta_de_recusa(recusa: RecusaDoAssistente) -> Response:
    corpo = RecusaDoAssistenteOutSerializer({"code": recusa.codigo, "detail": str(recusa.detalhe)})
    return Response(corpo.data, status=STATUS_DA_RECUSA[recusa.codigo])
