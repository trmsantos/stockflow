"""`/api/v1/documents` — os sete endpoints da decisão 9 da ADR 0021.

```
POST   /api/v1/documents                      201 DocumentoOut  (slot, com ou sem ficheiro)
POST   /api/v1/documents/<id>/files           201|200 DocumentoOut  (multipart, um ficheiro)
POST   /api/v1/documents/<id>/closing         200 DocumentoOut  (repetível)
GET    /api/v1/documents                      lista paginada
GET    /api/v1/documents/<id>                 200 DocumentoOut  (o alvo do polling, ADR 0020 d.3)
GET    /api/v1/documents/<id>/pages/<n>/image 200 image/webp    (inline, nosniff, com âmbito)
DELETE /api/v1/documents/<id>                 204               (descarta)
```

Views finas: cada uma valida com um serializer, chama **uma** função de
`services.py` e serializa. Nenhuma regra de negócio vive aqui, e o único
conhecimento de domínio deste ficheiro é o mapa de códigos de recusa para status
HTTP — que é transporte, e é por isso que vive do lado do transporte.

## Permissões: qualquer membro activo, e o que isso decide e não decide

`IsAuthenticated` + `PertenceAoTenant`, sem `TemPapel` (ADR 0021, decisão 9, pela
razão da decisão 1b da ADR 0020: *"receber mercadoria é trabalho de quem está
lá"*). O `has_object_permission` do `PertenceAoTenant` compara
`obj.tenant_id == request.tenant.id` em todas as operações que recebem um `pk`,
como o SECURITY.md §5 exige.

**O `DELETE` fica com a mesma permissão, e isso é uma escolha por omissão e não
uma decisão.** A terceira pergunta que a ADR 0021 deixou ao dono é exactamente
esta — *"quem pode apagar um documento que entrou errado?"* — e diz que é a única
permissão desta fatia que não é óbvia. Até haver resposta vale o default da
decisão 9 (qualquer membro activo), e o que o torna aceitável é o raio de
explosão: o descarte é **suave** (`discarded_at`), não apaga bytes de um
documento com páginas, e não existe nenhum caminho daqui ao ledger.

## As três redes do isolamento, e porque é que o 404 é a resposta certa

O `get_queryset` filtra por `request.tenant.id`, a política de RLS filtra por
`app.tenant_id`, e o `PertenceAoTenant` compara no caminho do objecto. A
consequência visível é que o `id` de um documento de outro estabelecimento dá
**404 e não 403**: a linha não é legível, logo não há objecto sobre o qual negar,
e um 403 confirmaria que aquele documento existe.

## O throttle só nas escritas

`ScopedRateThrottle` nas escritas (ADR 0021, decisão 9; ADR 0020, consequências),
porque cada página aceite custa uma rasterização e uma chamada a LLM a jusante.
**Não** nas leituras: o `GET` do documento é o alvo do polling de 2 segundos da
decisão 3 da ADR 0020 — 30 pedidos por minuto, dentro dos 600/min do
`UserRateThrottle` por omissão — e pô-lo no mesmo balde das escritas fazia o
polling comer o orçamento dos uploads.
"""

from __future__ import annotations

from django.db.models import QuerySet
from django.http import FileResponse, Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle

from apps.accounts.api import PertenceAoTenant, membership_atual, utilizador_atual
from apps.purchasing.ficheiros import caminho_dentro_do_media
from apps.purchasing.models import InvoiceDocument, Receipt, ReceiptLine
from apps.purchasing.selectors import (
    com_paginas,
    compor,
    compor_muitos,
    documentos_do_ambito,
    documentos_visiveis,
    pagina_por_posicao,
    preco_historico,
    resumo_de_recebidas,
)
from apps.purchasing.serializers import (
    CabecalhoInSerializer,
    DocumentoInSerializer,
    DocumentoOutSerializer,
    FicheiroDeDocumentoInSerializer,
    LinhaInSerializer,
    LinhaOutSerializer,
    RececaoInSerializer,
    RececaoOutSerializer,
    RecusaDeDocumentoOutSerializer,
    ResumoDeRececoesOutSerializer,
    RevisaoDeLinhaInSerializer,
    TemperaturaInSerializer,
)
from apps.purchasing.services import (
    CODIGO_DOCUMENTO_DESCARTADO,
    CODIGO_DOCUMENTO_FECHADO,
    CODIGO_DOCUMENTO_SEM_PAGINAS,
    CODIGO_PAGINAS_EXCEDIDAS,
    CriacaoDeRececaoJaExiste,
    RecusaDeDocumento,
    SemLinhasRevistas,
    anexar_ficheiro,
    apagar_rascunho,
    confirmar_rececao,
    criar_documento,
    criar_rececao,
    descartar_documento,
    fechar_documento,
    registar_temperatura,
    rever_linha,
)

__all__ = ["STATUS_DA_RECUSA_DE_DOCUMENTO", "DocumentoViewSet"]

#: O código de recusa em status HTTP. Fechado contra
#: `CODIGOS_DE_RECUSA_DE_DOCUMENTO` por um teste: um código sem entrada aqui
#: apareceria como 500.
STATUS_DA_RECUSA_DE_DOCUMENTO: dict[str, int] = {
    CODIGO_DOCUMENTO_FECHADO: status.HTTP_409_CONFLICT,
    CODIGO_DOCUMENTO_DESCARTADO: status.HTTP_409_CONFLICT,
    CODIGO_DOCUMENTO_SEM_PAGINAS: status.HTTP_409_CONFLICT,
    CODIGO_PAGINAS_EXCEDIDAS: status.HTTP_400_BAD_REQUEST,
}

#: O balde do throttle das escritas. Nome em português porque é um nome interno e
#: não contrato; o limite está no `DEFAULT_THROTTLE_RATES` do `base.py`.
AMBITO_DO_THROTTLE = "documentos"


@extend_schema_view(
    # As descrições vão explícitas, pela razão escrita no `ConviteViewSet` do
    # `accounts`: sem elas o drf-spectacular usa o docstring **da classe** como
    # descrição de cada operação, e este tem dezenas de linhas sobre isolamento e
    # throttle que não são contrato.
    list=extend_schema(
        operation_id="documentos_listar",
        summary="Documentos de fornecedor do estabelecimento ativo",
        description=(
            "Os documentos com pelo menos uma página, mais recentes primeiro, "
            "paginados. **Um slot sem páginas nunca aparece aqui** e um "
            "documento descartado também não — para esses há o `GET` por `id`, "
            "que é o alvo do polling enquanto a fotografia não chega."
        ),
        responses={status.HTTP_200_OK: DocumentoOutSerializer(many=True)},
    ),
    retrieve=extend_schema(
        operation_id="documentos_ler",
        summary="Um documento, com páginas e o que o modelo leu",
        description=(
            "O alvo do polling do bloco do QR (2 s enquanto o bloco está "
            "aberto, com desistência aos 3 minutos). Serve **também** um slot "
            "ainda sem páginas e um documento descartado: é precisamente esse o "
            "estado que o desktop está a sondar."
        ),
        responses={status.HTTP_200_OK: DocumentoOutSerializer},
    ),
    create=extend_schema(
        operation_id="documentos_criar",
        summary="Abrir um documento — com ficheiro, ou vazio para captura",
        description=(
            "Com `ficheiro`, é o upload de um só gesto: o documento nasce "
            "**fechado** e o trabalho fica agendado. Sem `ficheiro`, é o slot "
            "que o QR nomeia: nasce aberto, espera 15 minutos pela primeira "
            "página e é fechado por uma pessoa."
        ),
        request={"multipart/form-data": DocumentoInSerializer},
        responses={
            status.HTTP_201_CREATED: DocumentoOutSerializer,
            status.HTTP_400_BAD_REQUEST: RecusaDeDocumentoOutSerializer,
        },
    ),
    destroy=extend_schema(
        operation_id="documentos_descartar",
        summary="Descartar um documento",
        description=(
            "Descarte **suave**: a linha fica com `discarded_at` e sai da lista. "
            "Os bytes só são apagados se o documento não tiver páginas — o "
            "original de um documento fiscal não se apaga enquanto não houver "
            "política de retenção."
        ),
        responses={status.HTTP_204_NO_CONTENT: None},
    ),
)
class DocumentoViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """`/api/v1/documents` — abrir, anexar, fechar, ler, descartar.

    Sem `update` e sem `partial_update`: um documento não se edita. O que muda
    nele são três transições com regras — `files`, `closing` e o descarte — e
    nenhuma delas é um `PATCH` de campos.

    O `queryset` de classe nunca é usado (o `get_queryset` substitui-o) e existe
    por duas razões, as mesmas do `ConviteViewSet`: dá ao drf-spectacular o
    modelo de onde tirar o tipo do `id` no path, e faz a omissão falhar fechado —
    se alguém remover o `get_queryset`, o endpoint devolve uma lista vazia em vez
    dos documentos de todos os estabelecimentos.
    """

    permission_classes = [IsAuthenticated, PertenceAoTenant]
    serializer_class = DocumentoOutSerializer
    queryset = InvoiceDocument.objects.none()
    #: `MultiPartParser` **e** `JSONParser`: o `files` leva um ficheiro e o
    #: `closing` não leva corpo nenhum. O `FormParser` fica de fora — um corpo
    #: `urlencoded` não transporta ficheiros e aceitá-lo era superfície a mais.
    parser_classes = [MultiPartParser, JSONParser]
    throttle_scope = AMBITO_DO_THROTTLE

    def get_throttles(self) -> list[BaseThrottle]:
        """O `ScopedRateThrottle` só nas escritas — ver o docstring do módulo."""
        if self.request.method in SAFE_METHODS:
            return super().get_throttles()
        return [*super().get_throttles(), ScopedRateThrottle()]

    def get_queryset(self) -> QuerySet[InvoiceDocument]:
        """A segunda rede, ao lado da política (ver o docstring da classe).

        Duas querysets e não uma: a lista esconde os slots vazios e os
        descartados, e o caminho do objecto (`retrieve`, as acções, o `destroy`)
        **não** — senão o polling não encontrava o slot que está a sondar e o
        telemóvel não conseguia anexar-lhe uma página.
        """
        if self.action == "list":
            return documentos_visiveis(tenant_id=self.request.tenant.id)
        return documentos_do_ambito(tenant_id=self.request.tenant.id)

    # -----------------------------------------------------------------------
    # Leitura
    # -----------------------------------------------------------------------
    def list(self, request: Request, *args: object, **kwargs: object) -> Response:
        """A lista, composta em lote: **uma** chamada ao porto por página.

        Reimplementada em vez de usar o `ListModelMixin` por uma razão só: a
        composição com a extração tem de acontecer sobre a página inteira. Com o
        mixin, o serializer recebia documentos um a um e cada um atravessaria a
        fronteira do `agents` por sua conta — cinquenta queries por página, que é
        o N+1 na sua forma mais cara.
        """
        documentos = self.filter_queryset(self.get_queryset())
        pagina = self.paginate_queryset(documentos)
        compostos = compor_muitos(
            tenant_id=request.tenant.id,
            documentos=list(documentos if pagina is None else pagina),
        )
        dados = DocumentoOutSerializer(
            compostos, many=True, context=self.get_serializer_context()
        )
        if pagina is None:
            return Response(dados.data)
        return self.get_paginated_response(dados.data)

    def retrieve(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Um documento. `get_object()` corre as permissões de objecto."""
        return self._resposta(self.get_object(), status.HTTP_200_OK)

    # -----------------------------------------------------------------------
    # Escrita
    # -----------------------------------------------------------------------
    def create(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Abre um documento, com ficheiro ou sem ele."""
        corpo = DocumentoInSerializer(data=request.data)
        corpo.is_valid(raise_exception=True)
        utilizador = utilizador_atual(request)
        pertenca = membership_atual(request)
        try:
            documento = criar_documento(
                tenant_id=request.tenant.id,
                created_by_id=None if utilizador is None else utilizador.id,
                created_by_name="" if pertenca is None else pertenca.display_name,
                ficheiro=corpo.validated_data.get("ficheiro"),
            )
        except RecusaDeDocumento as recusa:
            return _resposta_de_recusa(recusa)
        return self._resposta(documento, status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="documentos_anexar_ficheiro",
        summary="Anexar um ficheiro (uma fotografia, ou um PDF)",
        description=(
            "Um ficheiro por pedido. **201 na primeira vez e 200 na repetição**: "
            "os mesmos bytes no mesmo documento não criam uma segunda página, e "
            "o código de status é o que torna essa idempotência observável — uma "
            "retentativa numa rede má não deve parecer um erro."
        ),
        request={"multipart/form-data": FicheiroDeDocumentoInSerializer},
        responses={
            status.HTTP_201_CREATED: DocumentoOutSerializer,
            status.HTTP_200_OK: DocumentoOutSerializer,
            status.HTTP_400_BAD_REQUEST: RecusaDeDocumentoOutSerializer,
            status.HTTP_409_CONFLICT: RecusaDeDocumentoOutSerializer,
        },
    )
    @action(detail=True, methods=["post"], url_path="files", url_name="ficheiros")
    def ficheiros(self, request: Request, pk: str | None = None) -> Response:
        """Anexa um ficheiro ao documento."""
        documento = self.get_object()
        corpo = FicheiroDeDocumentoInSerializer(data=request.data)
        corpo.is_valid(raise_exception=True)
        try:
            novo = anexar_ficheiro(
                tenant_id=request.tenant.id,
                documento=documento,
                ficheiro=corpo.validated_data["ficheiro"],
            )
        except RecusaDeDocumento as recusa:
            return _resposta_de_recusa(recusa)
        codigo = status.HTTP_201_CREATED if novo else status.HTTP_200_OK
        return self._resposta(documento, codigo)

    @extend_schema(
        operation_id="documentos_fechar",
        summary="Fechar o documento: não vêm mais páginas",
        description=(
            "Repetível dentro do mesmo estado: fechar duas vezes devolve 200 e "
            "não agenda trabalho duas vezes. Um documento sem páginas não se "
            "fecha — morre pelo relógio."
        ),
        request=None,
        responses={
            status.HTTP_200_OK: DocumentoOutSerializer,
            status.HTTP_409_CONFLICT: RecusaDeDocumentoOutSerializer,
        },
    )
    @action(detail=True, methods=["post"], url_path="closing", url_name="fecho")
    def fecho(self, request: Request, pk: str | None = None) -> Response:
        """Fecha o documento e agenda o trabalho, uma vez."""
        try:
            documento = fechar_documento(
                tenant_id=request.tenant.id, documento=self.get_object()
            )
        except RecusaDeDocumento as recusa:
            return _resposta_de_recusa(recusa)
        return self._resposta(documento, status.HTTP_200_OK)

    def perform_destroy(self, instance: InvoiceDocument) -> None:
        """O `DELETE` descarta; não apaga a linha."""
        descartar_documento(tenant_id=self.request.tenant.id, documento=instance)

    # -----------------------------------------------------------------------
    # Os bytes da imagem
    # -----------------------------------------------------------------------
    @extend_schema(
        operation_id="documentos_imagem_da_pagina",
        summary="A imagem normalizada de uma página",
        description=(
            "Servida por esta view e nunca pelo proxy: o `MEDIA_URL` não tem "
            "valor e o `/media/` não é encaminhado (ADR 0020, decisão 4). "
            "`inline`, `nosniff`, `Cache-Control: private`. 404 enquanto a "
            "página não estiver normalizada — e hoje nenhuma está, porque não há "
            "rasterizador nas dependências deste projecto."
        ),
        parameters=[
            OpenApiParameter(
                name="posicao",
                location=OpenApiParameter.PATH,
                type=OpenApiTypes.INT,
                description="A ordem da página dentro do documento, a começar em 1.",
            )
        ],
        responses={(status.HTTP_200_OK, "image/webp"): OpenApiTypes.BINARY},
    )
    @action(
        detail=True,
        methods=["get"],
        # `{1,4}` e não `+`: um inteiro de mais de 4300 dígitos levanta
        # `ValueError` no `int()` desde o Python 3.12 e sai 500. O documento tem
        # dez páginas, logo quatro dígitos é folga de três ordens de grandeza.
        url_path=r"pages/(?P<posicao>[0-9]{1,4})/image",
        url_name="imagem",
    )
    def imagem(
        self, request: Request, pk: str | None = None, posicao: str | None = None
    ) -> FileResponse:
        """Os bytes da imagem de uma página, dentro do âmbito.

        Corre o `get_object()` primeiro — e é isso que lhe dá as permissões de
        objecto e o 404 de um documento de outro estabelecimento. A página é
        depois procurada pela posição, e as três situações que têm de ser
        indistinguíveis de fora dão o mesmo 404: a página não existe, não está
        normalizada, ou os bytes desapareceram do disco.

        `FileResponse` e não um corpo em memória: um ficheiro de página pode ter
        megabytes e o `FileResponse` entrega-o por blocos, com o `Content-Length`
        que o cliente precisa para mostrar progresso.
        """
        documento = self.get_object()
        pagina = pagina_por_posicao(
            tenant_id=request.tenant.id,
            documento_id=documento.id,
            posicao=int(posicao or 0),
        )
        if pagina is None or not pagina.image_path:
            raise Http404
        # `caminho_dentro_do_media` e não `Path(MEDIA_ROOT) / x`: é a função que o
        # `services.py` escreveu para ser "a última linha antes de um `open()`", e
        # esta era a única das quatro aberturas do módulo que não a usava. Hoje o
        # `image_path` é gerado a partir de uuid e não vem do cliente — mas um
        # `Path(raiz) / x` com `x` absoluto devolve `x`, e o que protegia era uma
        # invariante a três ficheiros de distância em vez da verificação que já
        # existe aqui ao lado.
        try:
            caminho = caminho_dentro_do_media(pagina.image_path)
        except ValueError:
            raise Http404 from None
        if not caminho.is_file():
            raise Http404
        resposta = FileResponse(caminho.open("rb"), content_type="image/webp")
        # `inline` e não `attachment`: isto é a imagem que o ecrã de revisão
        # mostra. O original sai por uma acção explícita, com `attachment` e
        # `octet-stream` (ADR 0020, decisão 5) — acção que **não existe** nesta
        # fatia, porque é a segunda pergunta por responder do dono.
        resposta["Content-Disposition"] = "inline"
        resposta["X-Content-Type-Options"] = "nosniff"
        # `private` porque é conteúdo de um estabelecimento e não pode entrar em
        # cache partilhada; `immutable` porque o caminho identifica a página e a
        # imagem de uma página normalizada não muda — uma reabertura acrescenta
        # páginas, não substitui as que já lá estavam.
        resposta["Cache-Control"] = "private, max-age=86400, immutable"
        return resposta

    # -----------------------------------------------------------------------
    # Privado
    # -----------------------------------------------------------------------
    def _resposta(self, documento: InvoiceDocument, codigo: int) -> Response:
        """O `DocumentoOut` de um documento, recarregado com as colecções.

        Recarrega de propósito: depois de uma escrita, a instância em memória não
        tem o prefetch das páginas nem dos ficheiros, e serializá-la assim pagava
        uma query por colecção **e** servia a ordem errada. Uma leitura a mais
        por escrita é o preço certo por uma resposta completa, que é o que evita
        o segundo pedido do cliente.

        No `retrieve` isto custa uma leitura por `pk` a mais do que o estritamente
        necessário (o `get_object()` já leu a linha, sem as colecções). É o preço
        de haver **um** caminho para montar o `DocumentoOut` em vez de dois, e é
        uma query por chave primária: no polling de 2 s da ADR 0020 são 30 por
        minuto, contra os 600/min do balde do utilizador.
        """
        recarregado = com_paginas(
            tenant_id=self.request.tenant.id, documento_id=documento.id
        )
        if recarregado is None:
            raise Http404
        completo = compor(tenant_id=self.request.tenant.id, documento=recarregado)
        dados = DocumentoOutSerializer(completo, context=self.get_serializer_context())
        return Response(dados.data, status=codigo)


def _resposta_de_recusa(recusa: RecusaDeDocumento) -> Response:
    """O corpo de uma recusa, com o status que o mapa lhe dá.

    Um código fora do mapa seria um `KeyError` e portanto um 500 — e é por isso
    que o mapa é afirmado contra a lista fechada do `services.py` num teste, em
    vez de ter um default silencioso aqui.
    """
    corpo = RecusaDeDocumentoOutSerializer(
        {"code": recusa.codigo, "detail": str(recusa.detalhe)}
    )
    return Response(corpo.data, status=STATUS_DA_RECUSA_DE_DOCUMENTO[recusa.codigo])


# ============================================================================
# Receção de mercadoria (fatia 2, parte B)
# ============================================================================


@extend_schema_view(
    list=extend_schema(
        parameters=[
            # O terceiro argumento é o `location`; com `OpenApiTypes.STR` no lugar
            # dele o `spectacular` morria a serializar o enum para YAML.
            OpenApiParameter("estado", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
        ]
    ),
)
class RececaoViewSet(viewsets.ModelViewSet):
    """ViewSet para receções de mercadoria."""

    permission_classes = [IsAuthenticated, PertenceAoTenant]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "rececoes"

    def get_queryset(self) -> QuerySet:
        """Filtrado por tenant."""
        return Receipt.objects.filter(tenant_id=self.request.tenant.id).prefetch_related("lines")

    def get_serializer_class(self):
        """Serializers por ação."""
        if self.action in ["create"]:
            return RececaoInSerializer
        elif self.action in ["partial_update"]:
            return CabecalhoInSerializer
        else:
            return RececaoOutSerializer

    def retrieve(self, request, *args, **kwargs):
        """GET /receipts/{id} — retorna uma receção com estrutura completa."""
        receipt = self.get_object()
        output = RececaoOutSerializer(self._compor_rececao(receipt))
        return Response(output.data)

    def list(self, request, *args, **kwargs):
        """GET /receipts — lista paginada."""
        estado = request.query_params.get("estado", None)
        page = int(request.query_params.get("page", 1))

        queryset = self.get_queryset()

        if estado == "revisao":
            queryset = queryset.filter(confirmed_at__isnull=True)
        elif estado == "hoje":
            from django.utils import timezone
            today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            queryset = queryset.filter(confirmed_at__gte=today)

        # Ordenação
        queryset = queryset.order_by("-received_at")

        # Paginação
        page_size = 50
        offset = (page - 1) * page_size
        items = queryset[offset : offset + page_size]

        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        """POST /receipts — cria receção."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            receipt = criar_rececao(
                tenant_id=request.tenant.id,
                **serializer.validated_data,
            )
            output = RececaoOutSerializer(self._compor_rececao(receipt))
            return Response(output.data, status=status.HTTP_201_CREATED)
        except CriacaoDeRececaoJaExiste as e:
            # Repetição com documento já existente
            receipt = Receipt.objects.get(pk=e.receipt_id)
            output = RececaoOutSerializer(self._compor_rececao(receipt))
            return Response(output.data, status=status.HTTP_200_OK)

    def partial_update(self, request, pk=None, *args, **kwargs):
        """PATCH /receipts/{id} — atualiza cabeçalho."""
        receipt = self.get_object()

        if receipt.confirmed_at:
            return Response(
                {"code": "rececao_confirmada", "detail": "Receipt is already confirmed"},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Atualizar apenas zona da pessoa
        for field in ["supplier_id", "doc_type", "received_at", "location_id"]:
            if field in serializer.validated_data:
                setattr(receipt, field, serializer.validated_data[field])
        receipt.save()

        output = RececaoOutSerializer(self._compor_rececao(receipt))
        return Response(output.data)

    def destroy(self, request, pk=None, *args, **kwargs):
        """DELETE /receipts/{id} — apaga rascunho."""
        receipt = self.get_object()

        if receipt.confirmed_at:
            return Response(
                {"code": "rececao_confirmada", "detail": "Receipt is already confirmed"},
                status=status.HTTP_409_CONFLICT,
            )

        apagar_rascunho(receipt_id=receipt.id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"])
    def lines(self, request, pk=None):
        """GET/POST /receipts/{id}/lines — lista/cria linhas."""
        receipt = self.get_object()

        if request.method == "POST":
            serializer = LinhaInSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            # Criar linha
            position = receipt.lines.count() + 1
            linha = ReceiptLine.objects.create(
                tenant_id=request.tenant.id,
                receipt_id=receipt.id,
                position=position,
                **serializer.validated_data,
            )

            output = LinhaOutSerializer(self._compor_linha(linha))
            return Response(output.data, status=status.HTTP_201_CREATED)

        # GET
        linhas = receipt.lines.all()
        serializer = LinhaOutSerializer(
            [self._compor_linha(item) for item in linhas], many=True
        )
        return Response({
            "count": linhas.count(),
            "results": serializer.data
        })

    @action(detail=True, methods=["post"], url_path=r"lines/(?P<linha_id>[^/.]+)/confirmation")
    def line_confirmation(self, request, pk=None, linha_id=None):
        """POST /receipts/{id}/lines/{linha}/confirmation — revê linha."""
        receipt = self.get_object()

        if receipt.confirmed_at:
            return Response(
                {"code": "rececao_confirmada", "detail": "Receipt is already confirmed"},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            linha = ReceiptLine.objects.get(pk=linha_id, receipt_id=receipt.id)
        except ReceiptLine.DoesNotExist:
            raise Http404 from None

        serializer = RevisaoDeLinhaInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Rever linha
        linha = rever_linha(
            receipt_id=receipt.id,
            linha_id=linha.id,
            reviewed_by_id=request.user.id,
            reviewed_by_name=request.user.email,
            **serializer.validated_data,
        )

        output = LinhaOutSerializer(self._compor_linha(linha))
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def temperature(self, request, pk=None):
        """POST /receipts/{id}/temperature — registra temperatura."""
        receipt = self.get_object()

        if receipt.confirmed_at:
            return Response(
                {"code": "rececao_confirmada", "detail": "Receipt is already confirmed"},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = TemperaturaInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        receipt = registar_temperatura(
            receipt_id=receipt.id,
            measured_by_name=request.user.get_full_name() or request.user.username,
            **serializer.validated_data,
        )

        output = RececaoOutSerializer(self._compor_rececao(receipt))
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def confirmation(self, request, pk=None):
        """POST /receipts/{id}/confirmation — confirma receção."""
        receipt = self.get_object()

        try:
            receipt = confirmar_rececao(
                receipt_id=receipt.id,
                confirmed_by_id=request.user.id,
                confirmed_by_name=request.user.email,
            )
            output = RececaoOutSerializer(self._compor_rececao(receipt))
            return Response(output.data, status=status.HTTP_201_CREATED)
        except SemLinhasRevistas:
            return Response(
                {"code": "sem_linhas_revistas", "detail": "No reviewed lines"},
                status=status.HTTP_409_CONFLICT,
            )

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """GET /receipts/summary — resumo de receções."""
        resumo = resumo_de_recebidas(tenant_id=request.tenant.id)
        serializer = ResumoDeRececoesOutSerializer(resumo)
        return Response(serializer.data)

    # -----------------------------------------------------------------------
    # Privado
    # -----------------------------------------------------------------------

    def _compor_rececao(self, receipt: Receipt) -> dict:
        """Compor resposta de receção com dados relacionados."""
        from apps.catalog import api as catalog_api
        from apps.inventory import api as inventory_api

        # Recarregar com linhas
        receipt = Receipt.objects.prefetch_related("lines").get(pk=receipt.id)

        # Buscar dados relacionados
        linhas = list(receipt.lines.all())
        product_ids = [item.product_id for item in linhas if item.product_id]
        location_ids = [receipt.location_id] + [
            item.location_id for item in linhas if item.location_id
        ]

        produtos = catalog_api.produtos_por_id(tenant_id=receipt.tenant_id, ids=product_ids)
        locais = inventory_api.localizacoes_por_id(tenant_id=receipt.tenant_id, ids=location_ids)

        # Compor dados
        dados = {
            "receipt": receipt,
            "produtos": produtos,
            "locais": locais,
            "linhas": [self._compor_linha(item, produtos, locais) for item in linhas],
        }

        return dados

    def _compor_linha(self, linha: ReceiptLine, produtos=None, locais=None) -> dict:
        """Compor resposta de linha."""
        from apps.catalog import api as catalog_api
        from apps.inventory import api as inventory_api

        if not produtos:
            product_ids = [linha.product_id] if linha.product_id else []
            produtos = catalog_api.produtos_por_id(tenant_id=linha.tenant_id, ids=product_ids)

        if not locais:
            locais = inventory_api.localizacoes_por_id(
                tenant_id=linha.tenant_id, ids=[linha.location_id]
            )

        produto = produtos.get(linha.product_id) if linha.product_id else None

        # Calcular price_history
        price_history = None
        if linha.status == "confirmed" and produto:
            price_history = preco_historico(
                tenant_id=linha.tenant_id,
                product_id=linha.product_id,
                linha=linha,
            )

        # Stock quantity
        stock_quantity = None
        tem_quantidade = bool(linha.base_per_invoice_unit and linha.quantity_received)
        if linha.kind == "goods" and produto and tem_quantidade:
            base_qty = linha.quantity_received * linha.base_per_invoice_unit
            display_qty = base_qty / produto.display_factor if produto.display_factor else base_qty
            stock_quantity = {
                "base": base_qty,
                "base_unit": produto.base_unit,
                "display": display_qty,
                "display_unit": produto.display_unit,
            }

        return {
            "linha": linha,
            "produto": produto,
            "locais": locais,
            "price_history": price_history,
            "stock_quantity": stock_quantity,
        }
