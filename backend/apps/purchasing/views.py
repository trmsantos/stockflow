"""`/api/v1/documents` — os sete endpoints da decisão 9 da ADR 0021.

```
POST   /api/v1/documents                      201 DocumentoOut  (slot, com ou sem ficheiro)
POST   /api/v1/documents/<id>/files           201|200 DocumentoOut  (multipart, um ficheiro)
POST   /api/v1/documents/<id>/closing         200 DocumentoOut  (repetível)
GET    /api/v1/documents                      lista paginada
GET    /api/v1/documents/<id>                 200 DocumentoOut  (o alvo do polling, ADR 0020 d.3)
GET    /api/v1/documents/<id>/pages/<n>/image 200 image/webp    (inline, nosniff, com âmbito)
POST   /api/v1/documents/<id>/extraction      202 DocumentoOut  (voltar a ler; ADR 0031, E)
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

from decimal import Decimal

from django.conf import settings
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

from apps.accounts.api import (
    CHAVE_DE_EUROS,
    PertenceAoTenant,
    membership_atual,
    utilizador_atual,
    ve_euros,
)
from apps.purchasing.classificacao import avisos_da_linha
from apps.purchasing.ficheiros import caminho_dentro_do_media
from apps.purchasing.models import InvoiceDocument, Receipt, ReceiptLine
from apps.purchasing.selectors import (
    com_paginas,
    compor,
    compor_muitos,
    documentos_do_ambito,
    documentos_visiveis,
    inicio_do_dia_de_negocio,
    pagina_por_posicao,
    preco_historico,
    resumo_de_recebidas,
    ultimos_precos_por_codigo,
)
from apps.purchasing.serializers import (
    CabecalhoInSerializer,
    DocumentoInSerializer,
    DocumentoOutSerializer,
    FicheiroDeDocumentoInSerializer,
    LinhaInSerializer,
    LinhaOutSerializer,
    LinhasOutSerializer,
    RececaoInSerializer,
    RececaoOutSerializer,
    RecusaDeDocumentoOutSerializer,
    ResumoDeRececoesOutSerializer,
    RevisaoDeLinhaInSerializer,
    TemperaturaInSerializer,
)
from apps.purchasing.services import (
    CODIGO_DOCUMENTO_ANULADO,
    CODIGO_DOCUMENTO_DESCARTADO,
    CODIGO_DOCUMENTO_FECHADO,
    CODIGO_DOCUMENTO_SEM_PAGINAS,
    CODIGO_LINHA_SEM_ARTIGO,
    CODIGO_PAGINAS_EXCEDIDAS,
    CODIGO_RELEITURA_RECUSADA,
    DETALHE_LINHA_SEM_ARTIGO,
    CriacaoDeRececaoJaExiste,
    RececaoConfirmada,
    RecusaDeDocumento,
    SemArtigo,
    SemLinhasRevistas,
    acrescentar_linha,
    anexar_ficheiro,
    apagar_rascunho,
    confirmar_rececao,
    criar_documento,
    criar_rececao,
    descartar_documento,
    fechar_documento,
    pedir_releitura,
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
    CODIGO_DOCUMENTO_ANULADO: status.HTTP_409_CONFLICT,
    CODIGO_RELEITURA_RECUSADA: status.HTTP_409_CONFLICT,
}

#: O balde do throttle das escritas. Nome em português porque é um nome interno e
#: não contrato; o limite está no `DEFAULT_THROTTLE_RATES` do `base.py`.
AMBITO_DO_THROTTLE = "documentos"


def _nome_de_quem_age(request: Request) -> str:
    """O nome com que se carimba um registo: o da **pertença**, nunca o email.

    As colunas `..._by_name` deste módulo são servidas a **qualquer** membro do
    estabelecimento — incluindo o `staff` que só recebe mercadoria. Gravar lá o
    `request.user.email` punha o endereço de um colega na resposta de um `GET`,
    exactamente a fuga que o `accounts.api` evita ao servir o email só ao
    `OWNER`. O que se grava é o `display_name` da pertença, que é o nome da
    pessoa **naquele** tenant (ADR 0007) e o que o `criar_documento` já usava.

    **Sem nome, fica vazio**, e isso é a decisão: o email não é um nome e usá-lo
    como recurso era repor o defeito; inventar um ("Utilizador", o id) era pior,
    porque uma string fabricada parece um nome a quem lê a linha. A ausência
    lê-se como ausência — o `GET` serve `null` — e quem agiu continua gravado na
    coluna de chave estrangeira ao lado, que não sai no payload. Um
    `display_name` vazio é, de resto, uma pertença mal criada: o `accounts`
    pede-o em todos os caminhos que a criam.
    """
    pertenca = membership_atual(request)
    return "" if pertenca is None else pertenca.display_name


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

    def get_serializer_context(self) -> dict:
        """O contexto do DRF, mais a resposta a "este pedido vê euros?".

        A mesma linha da `RececaoViewSet`, e por uma razão que custou uma fuga:
        a adenda dos euros da ADR 0031 fechou os preços de uma **receção** e
        deixou aberto o painel do **documento**, que serve a mesma fatura e os
        mesmos preços — o `ExtracaoOut` leva o `total`, e cada `LinhaLidaOut`
        leva `unit_price`, `line_total` e `discount_pct`. Fechar uma porta e
        deixar a janela não é uma decisão parcial: é a decisão contornada.

        Chega a **todas** as rotas que servem um `DocumentoOut` — as cinco da
        decisão 9 (criar, anexar, fechar, ler, listar) mais o 202 da
        re-extração — porque as duas únicas construções do serializer
        (`list` e `_resposta`) passam por aqui. Sem esta função o default do
        `SemEurosParaQuemNaoVe` é **falso**, logo a omissão esconde os euros a
        toda a gente, incluindo ao dono: falha fechado, e o sintoma é um gerente
        a deixar de ver preços e nunca um colaborador a vê-los.
        """
        contexto = super().get_serializer_context()
        contexto[CHAVE_DE_EUROS] = ve_euros(self.request)
        return contexto

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
        try:
            documento = criar_documento(
                tenant_id=request.tenant.id,
                created_by_id=None if utilizador is None else utilizador.id,
                created_by_name=_nome_de_quem_age(request),
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

    @extend_schema(
        operation_id="documentos_reextrair",
        summary="Voltar a pedir a leitura deste documento ao modelo",
        description=(
            "O botão *tentar outra vez* do ramo de erro. **202**: a leitura "
            "fica aceite e não feita — quem a faz é o worker, e o cliente já "
            "sonda o `GET` do documento. Não é o `closing`, de propósito: o "
            "fecho é repetível para um duplo toque não pagar duas leituras, e "
            "este pedido **quer** pagar outra. 409 se já houver receção "
            "confirmada, se o documento já estiver a ser lido, ou se as "
            "tentativas tiverem acabado."
        ),
        request=None,
        responses={
            status.HTTP_202_ACCEPTED: DocumentoOutSerializer,
            status.HTTP_409_CONFLICT: RecusaDeDocumentoOutSerializer,
        },
    )
    @action(detail=True, methods=["post"], url_path="extraction", url_name="extracao")
    def extracao(self, request: Request, pk: str | None = None) -> Response:
        """Pede ao modelo que volte a ler o documento."""
        try:
            documento = pedir_releitura(
                tenant_id=request.tenant.id, documento=self.get_object()
            )
        except RecusaDeDocumento as recusa:
            return _resposta_de_recusa(recusa)
        return self._resposta(documento, status.HTTP_202_ACCEPTED)

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


# ---------------------------------------------------------------------------
# As recusas de uma receção, com a mesma forma das do documento
#
# `{code, detail}` e um status, que é o contrato que o `RecusaDeDocumentoOut`
# descreve e o que o frontend já lê: o `code` é para o ecrã **ramificar**, o
# `detail` é a frase que se mostra sem reescrever. A diferença para o
# `_resposta_de_recusa` é só de origem — ali o código vem dentro da exceção e
# tem um mapa fechado, aqui cada exceção de domínio tem a sua função. **São as
# duas o mesmo caminho e não um terceiro.**
#
# Toda a exceção de domínio que um serviço desta secção levanta tem de ter aqui
# a sua tradução: sem ela, o que o cliente recebe é um 500, e um portão humano
# que rebenta não é um portão.
# ---------------------------------------------------------------------------


def _resposta_de_rececao_confirmada() -> Response:
    """409. Escrever numa receção que já está no ledger.

    Os serviços levantam `RececaoConfirmada` e as views verificam o mesmo antes
    de chamar — a verificação poupa o trabalho, a exceção fecha a **corrida**:
    entre a leitura da view e a escrita do serviço cabe a confirmação de outra
    pessoa, e sem esta tradução essa corrida saía 500.
    """
    return Response(
        {"code": "rececao_confirmada", "detail": "Receipt is already confirmed"},
        status=status.HTTP_409_CONFLICT,
    )


def _resposta_de_linha_sem_artigo() -> Response:
    """400. A linha é mercadoria e ninguém disse qual é o artigo.

    Não é um erro do servidor: é **a pergunta que falta responder** no ecrã de
    revisão, e desde a fatia da extração (ADR 0031, decisão 5) é o estado normal
    da primeira fatura de um fornecedor novo. O `str()` resolve a frase aqui,
    dentro do pedido, com a língua que o `LocaleMiddleware` activou.
    """
    return Response(
        {"code": CODIGO_LINHA_SEM_ARTIGO, "detail": str(DETALHE_LINHA_SEM_ARTIGO)},
        status=status.HTTP_400_BAD_REQUEST,
    )


# ---------------------------------------------------------------------------
# Quem recebe mercadoria e quem vê quanto ela custou são duas perguntas
#
# As permissões da `RececaoViewSet` continuam `IsAuthenticated +
# PertenceAoTenant`, **sem `TemPapel`** (ADR 0021, decisão 9): receber
# mercadoria é trabalho de quem está lá, e o colaborador continua a conferir
# quantidades, a marcar linhas, a registar temperaturas e a confirmar.
#
# O que mudou a 2026-10-19, por decisão do dono — *"só owner e manager"* —, é o
# **dinheiro**: até à fatia da extração (ADR 0031) uma receção nascia sem linhas
# e não havia euros lá dentro; desde que o `criar_rececao` passou a semeá-las a
# partir da fatura, um `staff` via os preços de compra de um documento inteiro
# sem ninguém os ter escrito. Os campos de euros saem do payload por **ausência
# da chave** (`SemEurosParaQuemNaoVe`), e quem decide é o `ve_euros` do
# `accounts.api` — o mesmo predicado das contagens.
#
# É por isso que **todas** as respostas desta classe são serializadas com o
# `get_serializer_context()`: um serializer sem contexto falha fechado e não
# mostra euros a ninguém, incluindo ao dono. Construir um destes serializers sem
# `context` é o bug a procurar se um gerente deixar de ver preços.
#
# (O texto vive aqui e não no docstring da classe porque o drf-spectacular usa o
# docstring como **descrição da operação** no `schema.yml`, e vinte linhas sobre
# autorização não são contrato — é a mesma razão do `extend_schema_view` abaixo.)
# ---------------------------------------------------------------------------
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
    #: **O `PUT` sai do contrato** (ADR 0034, adenda de 29, decisão 18). O
    #: `ModelViewSet` ligava o `put` ao `update` herdado, que pede o serializer
    #: ao `get_serializer_class` e recebe o `RececaoOutSerializer` — um
    #: `serializers.Serializer` **sem `update()`** —, logo o `save()` levantava
    #: `NotImplementedError`. Os campos daquele serializer não são read-only, o
    #: que faz do **único corpo que o contrato publicado aceita** exactamente o
    #: que chegava ao 500: corpo errado → 400, corpo certo → 500, sem terceiro
    #: caminho. Não corrompia nada (o erro é antes de qualquer escrita), e é
    #: por isso que se fecha **tirando o método** e não escrevendo-lhe um
    #: corpo: o que estava partido era o contrato.
    #:
    #: É um atributo e não código porque é o atributo que **as duas pontas
    #: lêem**: o DRF compara-o no `dispatch` (405 antes de haver view) e o
    #: drf-spectacular cruza-o com as actions do router para decidir o que
    #: publica. Uma lista, dois efeitos, sem poderem divergir — o que o
    #: servidor recusa é o que o schema não tem. Um `update()` a levantar 405 à
    #: mão fazia o contrário: recusava com elegância uma rota que continuava
    #: publicada e que o `pnpm gen:api` continuava a gerar.
    #:
    #: O `patch` fica (é o que o ecrã usa para o cabeçalho, pelo
    #: `CabecalhoInSerializer`), o `trace` sai de caminho, e o `head` e o
    #: `options` ficam: o DRF mapeia `head` → `get` na própria `as_view` e o
    #: `OPTIONS` é o preflight e a metadata. O preço, dito: a lista vale para a
    #: classe inteira, logo uma action futura em `PUT` nasceria 405 até alguém
    #: mexer nesta linha. É a direcção certa para falhar.
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    # `none()` ao nível da classe, como o `LocalizacaoViewSet`: é daqui que o
    # drf-spectacular deriva o tipo do `pk` do caminho — o `get_queryset` lê o
    # `request.tenant`, que não existe na geração do schema, e sem isto o `id`
    # saía como "string" com um warning que o `--fail-on-warn` transforma em
    # exit 1. Nunca é usado para servir pedidos: o `get_queryset` sobrepõe-se.
    queryset = Receipt.objects.none()

    def get_queryset(self) -> QuerySet:
        """Filtrado por tenant."""
        return Receipt.objects.filter(tenant_id=self.request.tenant.id).prefetch_related("lines")

    def get_serializer_context(self) -> dict:
        """O contexto do DRF, mais a resposta a "este pedido vê euros?".

        Chega a **todos** os serializers desta classe, incluindo os filhos (o
        `LinhaOutSerializer` dentro do `LinhasOutSerializer`): o `context` de um
        serializer aninhado é o da raiz.
        """
        contexto = super().get_serializer_context()
        contexto[CHAVE_DE_EUROS] = ve_euros(self.request)
        return contexto

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
        output = RececaoOutSerializer(
            self._compor_rececao(receipt), context=self.get_serializer_context()
        )
        return Response(output.data)

    def list(self, request, *args, **kwargs):
        """GET /receipts — lista paginada na forma do DRF (`count`, `results`).

        Cada receção vai **composta** (`_compor_rececao`), como no `retrieve`:
        o `RececaoOutSerializer` lê `receipt.*` de um dicionário e não de um
        `Receipt` — passar-lhe as linhas cruas era o 500 que o ecrã Receber via.
        """
        estado = request.query_params.get("estado", None)

        queryset = self.get_queryset()

        if estado == "revisao":
            queryset = queryset.filter(confirmed_at__isnull=True)
        elif estado == "hoje":
            # **O início do dia de negócio**, e não a meia-noite (ADR 0028): o
            # rótulo do ecrã promete "desde as 04:00" e este filtro prometia
            # outra coisa entre a meia-noite e essa hora. É o mesmo selector
            # que a porta usa para a tool `rececoes(hoje)`, para as duas
            # respostas não divergirem.
            queryset = queryset.filter(
                confirmed_at__gte=inicio_do_dia_de_negocio(tenant_id=request.tenant.id)
            )

        queryset = queryset.order_by("-received_at")

        pagina = self.paginate_queryset(queryset)
        itens = pagina if pagina is not None else list(queryset)
        compostos = [self._compor_rececao(receipt) for receipt in itens]
        serializer = RececaoOutSerializer(
            compostos, many=True, context=self.get_serializer_context()
        )
        if pagina is not None:
            return self.get_paginated_response(serializer.data)
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
            output = RececaoOutSerializer(
                self._compor_rececao(receipt), context=self.get_serializer_context()
            )
            return Response(output.data, status=status.HTTP_201_CREATED)
        except CriacaoDeRececaoJaExiste as e:
            # Repetição com documento já existente
            receipt = Receipt.objects.get(pk=e.receipt_id)
            output = RececaoOutSerializer(
                self._compor_rececao(receipt), context=self.get_serializer_context()
            )
            return Response(output.data, status=status.HTTP_200_OK)
        except RecusaDeDocumento as recusa:
            # Hoje só uma: o QR diz que o documento foi **anulado** pelo
            # emissor, e um documento anulado não dá entrada a mercadoria
            # nenhuma (ADR 0021, adenda). Recusa e não aviso.
            return _resposta_de_recusa(recusa)

    def partial_update(self, request, pk=None, *args, **kwargs):
        """PATCH /receipts/{id} — atualiza cabeçalho."""
        receipt = self.get_object()

        if receipt.confirmed_at:
            return _resposta_de_rececao_confirmada()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Atualizar apenas zona da pessoa
        for field in ["supplier_id", "doc_type", "received_at", "location_id"]:
            if field in serializer.validated_data:
                setattr(receipt, field, serializer.validated_data[field])
        receipt.save()

        output = RececaoOutSerializer(
            self._compor_rececao(receipt), context=self.get_serializer_context()
        )
        return Response(output.data)

    def destroy(self, request, pk=None, *args, **kwargs):
        """DELETE /receipts/{id} — apaga rascunho."""
        receipt = self.get_object()

        if receipt.confirmed_at:
            return _resposta_de_rececao_confirmada()

        try:
            apagar_rascunho(receipt_id=receipt.id)
        except RececaoConfirmada:
            # A corrida: alguém confirmou a receção entre a leitura acima e a
            # releitura do serviço. O serviço recusa — o que não existia era a
            # tradução, e sem ela a corrida saía 500.
            return _resposta_de_rececao_confirmada()

        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        methods=["GET"],
        responses={status.HTTP_200_OK: LinhasOutSerializer},
    )
    @extend_schema(
        methods=["POST"],
        request=LinhaInSerializer,
        responses={status.HTTP_201_CREATED: LinhaOutSerializer},
    )
    @action(detail=True, methods=["get", "post"])
    def lines(self, request, pk=None):
        """GET/POST /receipts/{id}/lines — lista/cria linhas."""
        receipt = self.get_object()

        if request.method == "POST":
            serializer = LinhaInSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            try:
                linha = acrescentar_linha(
                    receipt_id=receipt.id, **serializer.validated_data
                )
            except RececaoConfirmada:
                return _resposta_de_rececao_confirmada()

            output = LinhaOutSerializer(
                self._compor_linha(linha), context=self.get_serializer_context()
            )
            return Response(output.data, status=status.HTTP_201_CREATED)

        # GET, **em lote**: sem isto eram cinco queries por linha, duas delas a
        # atravessar a fronteira de um módulo.
        compostas = self._compor_rececao(receipt)["linhas"]
        serializer = LinhaOutSerializer(
            compostas, many=True, context=self.get_serializer_context()
        )
        return Response({"count": len(compostas), "results": serializer.data})

    @extend_schema(
        parameters=[
            OpenApiParameter("linha_id", OpenApiTypes.UUID, OpenApiParameter.PATH, required=True),
        ],
        request=RevisaoDeLinhaInSerializer,
        responses={status.HTTP_201_CREATED: LinhaOutSerializer},
    )
    @action(detail=True, methods=["post"], url_path=r"lines/(?P<linha_id>[^/.]+)/confirmation")
    def line_confirmation(self, request, pk=None, linha_id=None):
        """POST /receipts/{id}/lines/{linha}/confirmation — revê linha."""
        receipt = self.get_object()

        if receipt.confirmed_at:
            return _resposta_de_rececao_confirmada()

        try:
            linha = ReceiptLine.objects.get(pk=linha_id, receipt_id=receipt.id)
        except ReceiptLine.DoesNotExist:
            raise Http404 from None

        serializer = RevisaoDeLinhaInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Rever linha. As duas exceções de domínio do `rever_linha` são
        # traduzidas aqui, e é esta tradução que faltava: sem ela, uma linha de
        # mercadoria por casar — o estado normal da primeira fatura de um
        # fornecedor novo (ADR 0031, decisão 5) — respondia 500 ao gesto de
        # confirmar, e um portão humano que rebenta não é um portão.
        try:
            linha = rever_linha(
                receipt_id=receipt.id,
                linha_id=linha.id,
                reviewed_by_id=request.user.id,
                reviewed_by_name=_nome_de_quem_age(request),
                **serializer.validated_data,
            )
        except SemArtigo:
            return _resposta_de_linha_sem_artigo()
        except RececaoConfirmada:
            # A mesma corrida do `destroy`: a verificação acima lê a receção
            # antes de o serviço a reler, e entre as duas cabe a confirmação de
            # outra pessoa.
            return _resposta_de_rececao_confirmada()

        output = LinhaOutSerializer(
            self._compor_linha(linha), context=self.get_serializer_context()
        )
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def temperature(self, request, pk=None):
        """POST /receipts/{id}/temperature — registra temperatura."""
        receipt = self.get_object()

        if receipt.confirmed_at:
            return _resposta_de_rececao_confirmada()

        serializer = TemperaturaInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        receipt = registar_temperatura(
            receipt_id=receipt.id,
            measured_by_name=_nome_de_quem_age(request),
            **serializer.validated_data,
        )

        output = RececaoOutSerializer(
            self._compor_rececao(receipt), context=self.get_serializer_context()
        )
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def confirmation(self, request, pk=None):
        """POST /receipts/{id}/confirmation — confirma receção."""
        receipt = self.get_object()

        try:
            receipt = confirmar_rececao(
                receipt_id=receipt.id,
                confirmed_by_id=request.user.id,
                confirmed_by_name=_nome_de_quem_age(request),
            )
            output = RececaoOutSerializer(
                self._compor_rececao(receipt), context=self.get_serializer_context()
            )
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
        # Os últimos preços por código, **em lote**: o aviso `preco_desviado` é
        # por linha e a alternativa era uma query por linha a atravessar o
        # histórico inteiro de uma receção de trinta linhas.
        precos = ultimos_precos_por_codigo(
            tenant_id=receipt.tenant_id,
            supplier_id=receipt.supplier_id,
            codes=[item.supplier_code for item in linhas if item.supplier_code],
            excepto_receipt_id=receipt.id,
        )

        embalagens = catalog_api.embalagens_por_id(
            tenant_id=receipt.tenant_id,
            ids=[item.packaging_id for item in linhas if item.packaging_id],
        )

        # Compor dados
        dados = {
            "receipt": receipt,
            "produtos": produtos,
            "locais": locais,
            "linhas": [
                self._compor_linha(item, produtos, locais, precos, embalagens)
                for item in linhas
            ],
        }

        return dados

    def _compor_linha(
        self, linha: ReceiptLine, produtos=None, locais=None, precos=None, embalagens=None
    ) -> dict:
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

        # A quantidade que esta linha mete no stock. O `quantity_received` **já
        # está em unidades base** — é dele que o ledger lê e dele que sai o
        # `unit_cost = line_total / quantity_received` (ADR 0023, decisão 3) —,
        # logo multiplicá-lo outra vez pelo `base_per_invoice_unit` dava o
        # quadrado da conversão: 25 000 g a virarem 625 000 000.
        stock_quantity = None
        if linha.kind == "goods" and produto and linha.quantity_received:
            base_qty = linha.quantity_received
            display_qty = base_qty / produto.display_factor if produto.display_factor else base_qty
            stock_quantity = {
                "base": base_qty,
                "base_unit": produto.base_unit,
                "display": display_qty,
                "display_unit": produto.display_unit,
            }

        # **Plano e com as chaves do `LinhaOutSerializer`.** Até 2026-10-19 esta
        # função devolvia `{"linha": …, "produto": …}` e o serializer declarava
        # `id`, `position`, `description`…: o `GET /receipts/<id>/lines` e a
        # revisão de uma linha respondiam **500** em todas as chamadas, e
        # nenhum teste os exercitava. O ecrã de revisão lê daqui.
        local = (locais or {}).get(linha.location_id)
        embalagem = None
        if linha.packaging_id:
            if embalagens is None:
                embalagens = catalog_api.embalagens_por_id(
                    tenant_id=linha.tenant_id, ids=[linha.packaging_id]
                )
            encontrada = embalagens.get(linha.packaging_id)
            if encontrada is not None and produto is not None:
                embalagem = {
                    "id": encontrada.id,
                    "label": encontrada.label,
                    "base_quantity": encontrada.base_quantity,
                    "base_unit": produto.base_unit,
                }
        return {
            # A linha crua fica na chave `linha` porque o `RececaoOutSerializer`
            # a lê para somar totais e contar o que falta rever. O DRF ignora
            # chaves que o serializer não declara, logo não sai no payload.
            "linha": linha,
            "id": linha.id,
            "position": linha.position,
            "description": linha.description,
            "product": linha.product_id,
            "product_name": produto.short_name if produto else None,
            "kind": linha.kind,
            "status": linha.status,
            "conservation": produto.conservation if produto else "ambient",
            "location": (
                {"id": local.id, "name": local.name}
                if local is not None
                else {"id": linha.location_id, "name": ""}
            ),
            "invoice_unit": linha.invoice_unit,
            "quantity_invoiced": linha.quantity_invoiced,
            "quantity_received": linha.quantity_received,
            "packaging": embalagem,
            "base_per_invoice_unit": linha.base_per_invoice_unit,
            "variable_weight": linha.variable_weight,
            "unit_price": linha.unit_price,
            "discount_pct": linha.discount_pct,
            "vat_rate": linha.vat_rate,
            "line_total": linha.line_total,
            "supplier_code": linha.supplier_code,
            "ean": linha.ean,
            "requires_lot": bool(produto.track_lots) if produto else False,
            "lot_code": linha.lot_code,
            "expires_at": linha.expires_at,
            "expiry_kind": (produto.expiry_kind if produto else None) or None,
            "reviewed_by": linha.reviewed_by_name or None,
            "reviewed_at": linha.reviewed_at,
            "movement": linha.movement_id,
            "price_history": price_history,
            "stock_quantity": stock_quantity,
            "warnings": list(
                avisos_da_linha(
                    kind=linha.kind,
                    quantity_invoiced=linha.quantity_invoiced,
                    unit_price=linha.unit_price,
                    line_total=linha.line_total,
                    vat_rate=linha.vat_rate,
                    base_per_invoice_unit=linha.base_per_invoice_unit,
                    extraction_confidence=linha.extraction_confidence,
                    limiar_de_confianca=Decimal(
                        settings.AGENTS_EXTRACTION_CONFIDENCE_THRESHOLD
                    ),
                    preco_de_referencia=(precos or {}).get(linha.supplier_code),
                )
            ),
        }
