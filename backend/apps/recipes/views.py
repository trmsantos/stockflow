"""O ViewSet das fichas técnicas (ADR 0035, fatia A).

Endpoints:

- `GET  /api/v1/recipes` — a lista, paginada, com o custo de ingredientes
- `POST /api/v1/recipes` — a ficha inteira, linhas incluídas
- `GET  /api/v1/recipes/{id}` — a ficha, com as linhas
- `PATCH /api/v1/recipes/{id}` — alterar; `lines` ausente não toca nas linhas

`http_method_names` fecha a classe nos cinco métodos: **sem `PUT`**, que seria um
método publicado sem quem o sirva (ADR 0034, decisão 18, a repetir-se), e **sem
`DELETE`**, porque uma receita não se apaga — arquiva-se com
`PATCH {is_active: false}`. Foi a ficha técnica de mercadoria que entrou no
ledger, e o precedente do artigo arquivado que responde 200 é o da ADR 0034,
decisão 13.

Todas as operações publicam `request=` e `responses=` (ADR 0035, decisão 7).
Sem eles o `drf-spectacular` cai no `get_serializer_class()` e publica a
**resposta** da classe como se fosse o pedido — foi a causa única das cinco
respostas erradas que a ADR 0034 deixou nomeadas como dívida. Um ViewSet novo não
tem desculpa para nascer assim.

## A assimetria de papéis é o espelho da das contagens

**Ler a ficha é dos três papéis** (decisão do dono, 2026-10-16): quem está na
cozinha precisa das quantidades para produzir, e o que o `staff` não vê são os
**euros**, que são uma coluna e não o recurso. **Escrever a ficha é
`owner|manager`**: a ficha é a definição do produto e do seu custo, e mudar uma
quantidade muda o custo de tudo o que dali sair.

Nas contagens é ao contrário — abrir e contar são de toda a gente e fechar é do
gabinete. Aqui o gabinete escreve a ficha e o campo produz a partir dela (a
produção é a fatia B e será dos três).

## O 404 é da política, não de uma comparação em Python

O `get_queryset` filtra pelo estabelecimento do pedido, logo o `id` de outro
tenant é **404** e não 403: 403 confirmaria que o objecto existe a quem o não
pode ver (SECURITY.md §5). A RLS é a primeira rede e isto é a segunda. O mesmo
vale para um `product` ou um `ingredient` de outro estabelecimento: o
`produtos_por_id` não os devolve, e o 404 sai daí.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ValidationError as DRFValidationError
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle

from apps.accounts.api import (
    CHAVE_DE_EUROS,
    Papel,
    PertenceAoTenant,
    TemPapel,
    ve_euros,
)
from apps.catalog.api import ProdutoResumo, produtos_por_id
from apps.recipes import selectors
from apps.recipes.api import fichas_das_receitas
from apps.recipes.models import Recipe
from apps.recipes.serializers import (
    ConflitoDeReceitaOutSerializer,
    ReceitaDetalheOutSerializer,
    ReceitaInSerializer,
    ReceitaPatchInSerializer,
    ReceitaResumoOutSerializer,
    compor_ficha,
    compor_resumo,
)
from apps.recipes.services import (
    CODIGO_RECEITA_JA_EXISTE,
    LinhaDaFicha,
    ReceitaJaExiste,
    actualizar_receita,
    criar_receita,
)
from apps.shared.serializers import em_unidade_pedida

#: O mesmo balde do catálogo, e pela mesma razão: uma ficha técnica é uma
#: **definição** e escreve-se às unidades por dia, não às centenas por minuto.
#: Um balde novo para quatro rotas era uma linha de configuração a mais sem
#: nenhum facto novo por trás.
AMBITO_THROTTLE_CATALOGO = "catalogo"

#: Quem escreve a ficha. Instanciada uma vez: a fábrica cria uma subclasse a
#: cada chamada, e duas subclasses iguais em dois sítios não ajudam ninguém.
SO_OWNER_OU_MANAGER = TemPapel.exige(Papel.OWNER, Papel.MANAGER)

#: Os dois valores do `?estado=`. Um terceiro é **400** e não uma lista a fingir
#: que filtrou: o conjunto é fechado e o cliente só envia estes dois.
ESTADOS_DA_LISTA = ("activas", "todas")

DETALHE_ESTADO_INVALIDO = _("Unknown state. Use activas or todas.")
DETALHE_UUID_INVALIDO = _("Not a valid UUID.")
DETALHE_JA_EXISTE = _("This product already has a recipe.")

#: As chaves por que o erro de unidade sai quando o que falhou foi a **fornada**
#: e não uma linha. O `em_unidade_pedida` fala em `unit`/`quantity` porque é a
#: linguagem de uma linha; aqui o campo do contrato chama-se outra coisa, e um
#: 400 que aponta para um campo que o corpo não tem é um 400 que ninguém
#: consegue corrigir.
_CHAVES_DA_FORNADA = {"unit": "batch_unit", "quantity": "batch_size"}

_P_Q = OpenApiParameter(
    "q",
    OpenApiTypes.STR,
    OpenApiParameter.QUERY,
    description="Casa no nome curto ou no SKU do **acabado**, por tokens.",
)
_P_INGREDIENTE = OpenApiParameter(
    "ingrediente",
    OpenApiTypes.UUID,
    OpenApiParameter.QUERY,
    description=(
        "Só as fichas que usam este artigo como ingrediente — a pergunta *«que "
        "receitas usam farinha»*. Um uuid inválido é 400."
    ),
)
_P_ESTADO = OpenApiParameter(
    "estado",
    OpenApiTypes.STR,
    OpenApiParameter.QUERY,
    enum=list(ESTADOS_DA_LISTA),
    description=(
        "`activas` (omissão) ou `todas`. As arquivadas entram **marcadas** pelo "
        "`is_active` e nunca escondidas: esconder uma ficha arquivada fazia "
        "*«não tenho essa receita»* mentir."
    ),
)


def _recusa(detalhe: Any) -> Response:
    return Response({"detail": str(detalhe)}, status=status.HTTP_400_BAD_REQUEST)


def _resposta_de_validacao(erro: ValidationError) -> Response:
    """400 na forma por campo do DRF, a partir de um `ValidationError` do Django.

    O DRF não converte o `ValidationError` do `django.core.exceptions`: deixá-lo
    subir era um 500 numa recusa de validação.
    """
    return Response(
        getattr(erro, "message_dict", {"detail": erro.messages}),
        status=status.HTTP_400_BAD_REQUEST,
    )


def _uuid_do_parametro(valor: str | None) -> UUID | None:
    if valor is None or valor == "":
        return None
    return UUID(valor)


def _em_base(
    valor: Decimal,
    *,
    unidade: str,
    produto: Any,
    chaves: Mapping[str, str] | None = None,
) -> Decimal:
    """`em_unidade_pedida`, com as chaves do erro traduzidas para este corpo."""
    try:
        return em_unidade_pedida(valor, unidade=unidade, produto=produto)
    except DRFValidationError as erro:
        if chaves is None or not isinstance(erro.detail, dict):
            raise
        raise DRFValidationError(
            {chaves.get(campo, campo): valores for campo, valores in erro.detail.items()}
        ) from None


@extend_schema_view(
    list=extend_schema(
        operation_id="receitas_listar",
        summary="As fichas técnicas do estabelecimento, com o custo de ingredientes",
        description=(
            "Uma linha por ficha, por ordem alfabética do acabado e com as "
            "arquivadas no fim. Os três euros (`batch_cost`, `unit_cost`, "
            "`display_cost`) **não vêm** para quem não é `owner` ou `manager`: "
            "a chave fica **ausente**, nunca `0` nem `null`."
        ),
        parameters=[_P_Q, _P_INGREDIENTE, _P_ESTADO],
        responses={200: ReceitaResumoOutSerializer(many=True)},
    ),
    create=extend_schema(
        operation_id="receitas_criar",
        summary="Gravar uma ficha técnica inteira, linhas incluídas",
        description=(
            "`409 receita_ja_existe` quando o artigo já tem ficha, com o `id` "
            "da que existe no corpo. `404` quando o `product` ou um "
            "`ingredient` não é legível neste estabelecimento. `400` para os "
            "números, para uma unidade que não é a base nem a de apresentação "
            "do artigo, para ingrediente repetido e para **ciclos** — o acabado "
            "em qualquer ponto do seu grafo transitivo de receitas."
        ),
        request=ReceitaInSerializer,
        responses={
            201: ReceitaDetalheOutSerializer,
            409: ConflitoDeReceitaOutSerializer,
        },
    ),
    retrieve=extend_schema(
        operation_id="receitas_obter",
        summary="A ficha técnica de uma receita, com as linhas",
        description=(
            "Uma receita **inactiva** responde 200 e nunca 404: mercadoria que "
            "existiu continua auditável."
        ),
        request=None,
        responses={200: ReceitaDetalheOutSerializer},
    ),
    partial_update=extend_schema(
        operation_id="receitas_atualizar",
        summary="Alterar a ficha; `lines` presente substitui as linhas todas",
        description=(
            "O campo `lines` **ausente** não toca nas linhas e `lines` "
            "**presente** substitui-as todas — é a única parte do contrato que "
            "não se adivinha. O `product` não é alterável: é a identidade da "
            "ficha. Arquivar é `{\"is_active\": false}`; não há `DELETE`."
        ),
        request=ReceitaPatchInSerializer,
        responses={200: ReceitaDetalheOutSerializer},
    ),
)
class ReceitaViewSet(viewsets.GenericViewSet):
    """As quatro rotas de uma ficha técnica.

    | rota | quem |
    |---|---|
    | `GET recipes` | todos |
    | `POST recipes` | owner, manager |
    | `GET recipes/{id}` | todos |
    | `PATCH recipes/{id}` | owner, manager |
    """

    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_classes = [IsAuthenticated, PertenceAoTenant]
    serializer_class = ReceitaResumoOutSerializer
    #: Vazia e como atributo de classe, não porque alguém a use — o
    #: `get_queryset` abaixo substitui-a sempre — mas porque o drf-spectacular
    #: lê o `queryset` da classe, fora de um pedido, para tipar o `{id}` do
    #: caminho. Sem ela o `self.request.tenant` não existe, a derivação falha e
    #: o schema sai com um warning, que é exit 1 no `spectacular --fail-on-warn`.
    queryset = Recipe.objects.none()
    throttle_scope = AMBITO_THROTTLE_CATALOGO

    def get_permissions(self):
        """Ler é dos três papéis; escrever é de `owner|manager` — ver o módulo."""
        if self.action in ("create", "partial_update"):
            return [IsAuthenticated(), PertenceAoTenant(), SO_OWNER_OU_MANAGER()]
        return [IsAuthenticated(), PertenceAoTenant()]

    def get_throttles(self) -> list[BaseThrottle]:
        """ScopedRateThrottle só nas escritas."""
        if self.request.method in SAFE_METHODS:
            return super().get_throttles()
        return [*super().get_throttles(), ScopedRateThrottle()]

    def get_queryset(self) -> QuerySet[Recipe]:
        """As receitas do estabelecimento activo, **sem filtrar pelo estado**.

        Este é o queryset do `get_object()`, e filtrá-lo por `is_active` fazia
        um `PATCH` sobre uma ficha arquivada responder 404 — exactamente a
        operação que a desarquiva. O filtro da lista vive no `list`, que é onde
        ele é uma pergunta.
        """
        return selectors.listar_receitas(
            tenant_id=self.request.tenant.id, incluir_inativas=True
        )

    def get_serializer_context(self) -> dict[str, Any]:
        """O contexto de serialização: quem vê euros, e nada mais.

        O default do `SemEurosParaQuemNaoVe` é **falso**, logo esquecer este
        contexto esconde dinheiro a toda a gente em vez de o mostrar a quem não
        deve — a direcção certa para falhar.
        """
        return {
            **super().get_serializer_context(),
            CHAVE_DE_EUROS: ve_euros(self.request),
        }

    # -- Leitura ------------------------------------------------------------
    def list(self, request: Request, *args, **kwargs) -> Response:
        """A lista paginada, com o custo de cada ficha calculado **em lote**."""
        estado = request.query_params.get("estado", ESTADOS_DA_LISTA[0])
        if estado not in ESTADOS_DA_LISTA:
            return _recusa(DETALHE_ESTADO_INVALIDO)
        try:
            ingrediente = _uuid_do_parametro(request.query_params.get("ingrediente"))
        except ValueError:
            return _recusa(DETALHE_UUID_INVALIDO)

        receitas = selectors.listar_receitas(
            tenant_id=request.tenant.id,
            q=request.query_params.get("q", "").strip(),
            ingrediente_id=ingrediente,
            incluir_inativas=estado == "todas",
        )
        pagina = self.paginate_queryset(receitas)
        fichas = fichas_das_receitas(tenant_id=request.tenant.id, receitas=pagina or [])
        corpo = ReceitaResumoOutSerializer(
            [compor_resumo(ficha) for ficha in fichas],
            many=True,
            context=self.get_serializer_context(),
        )
        return self.get_paginated_response(corpo.data)

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        """A ficha de uma receita. Inactiva responde 200, de outro tenant é 404."""
        return self._ficha(self.get_object(), status.HTTP_200_OK)

    # -- Escrita ------------------------------------------------------------
    def create(self, request: Request, *args, **kwargs) -> Response:
        """Grava a ficha inteira, de uma vez. 409 se o artigo já tiver uma."""
        entrada = ReceitaInSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data

        artigos = self._artigos(
            request,
            ids=[dados["product"], *(linha["ingredient"] for linha in dados["lines"])],
        )
        fornada = _em_base(
            dados["batch_size"],
            unidade=dados["batch_unit"],
            produto=artigos[dados["product"]],
            chaves=_CHAVES_DA_FORNADA,
        )
        linhas = self._linhas(dados["lines"], artigos=artigos)
        try:
            receita = criar_receita(
                tenant_id=request.tenant.id,
                product_id=dados["product"],
                batch_size=fornada,
                yield_factor=dados["yield_factor"],
                is_active=dados["is_active"],
                linhas=linhas,
            )
        except ReceitaJaExiste as erro:
            return Response(
                {
                    "code": CODIGO_RECEITA_JA_EXISTE,
                    "detail": str(DETALHE_JA_EXISTE),
                    "id": erro.recipe_id,
                },
                status=status.HTTP_409_CONFLICT,
            )
        except ValidationError as erro:
            return _resposta_de_validacao(erro)

        return self._ficha(
            selectors.receita_do_ambito(
                tenant_id=request.tenant.id, recipe_id=receita.pk
            ),
            status.HTTP_201_CREATED,
        )

    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        """Altera a ficha. `lines` ausente não lhes toca; presente substitui-as."""
        receita = self.get_object()
        entrada = ReceitaPatchInSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        dados = entrada.validated_data

        fornada = None
        if "batch_size" in dados:
            # O acabado já veio carregado pelo `select_related` do queryset: a
            # sua unidade não custa uma query.
            fornada = _em_base(
                dados["batch_size"],
                unidade=dados["batch_unit"],
                produto=receita.product,
                chaves=_CHAVES_DA_FORNADA,
            )
        linhas = None
        if "lines" in dados:
            artigos = self._artigos(
                request, ids=[linha["ingredient"] for linha in dados["lines"]]
            )
            linhas = self._linhas(dados["lines"], artigos=artigos)
        try:
            actualizar_receita(
                tenant_id=request.tenant.id,
                receita=receita,
                batch_size=fornada,
                yield_factor=dados.get("yield_factor"),
                is_active=dados.get("is_active"),
                linhas=linhas,
            )
        except ValidationError as erro:
            return _resposta_de_validacao(erro)

        return self._ficha(
            selectors.receita_do_ambito(
                tenant_id=request.tenant.id, recipe_id=receita.pk
            ),
            status.HTTP_200_OK,
        )

    # -- Andaimes -----------------------------------------------------------
    def _ficha(self, receita: Recipe | None, codigo: int) -> Response:
        """O corpo da ficha, pela **mesma** função que serve a linha da lista."""
        if receita is None:  # pragma: no cover - a receita acabou de ser lida
            raise Http404
        ficha = fichas_das_receitas(
            tenant_id=self.request.tenant.id, receitas=[receita]
        )[0]
        corpo = ReceitaDetalheOutSerializer(
            compor_ficha(ficha), context=self.get_serializer_context()
        )
        return Response(corpo.data, status=codigo)

    def _artigos(
        self, request: Request, *, ids: Sequence[UUID]
    ) -> Mapping[UUID, ProdutoResumo]:
        """Os artigos do corpo, **numa query**. O que não vier de lá é 404.

        404 e não 400 porque a pergunta *"este artigo existe?"* não tem resposta
        fora do estabelecimento: o `produtos_por_id` filtra por `tenant_id`
        dentro do âmbito e a política é quem não devolve a linha. Ninguém compara
        tenants em Python.
        """
        pedidos = list(dict.fromkeys(ids))
        artigos = produtos_por_id(tenant_id=request.tenant.id, ids=pedidos)
        if len(artigos) != len(pedidos):
            raise Http404
        return artigos

    def _linhas(
        self,
        linhas: Sequence[Mapping[str, Any]],
        *,
        artigos: Mapping[UUID, ProdutoResumo],
    ) -> list[LinhaDaFicha]:
        """As linhas já em unidade **base**, ou um 400 que diz **qual** falhou.

        O erro sai na forma de lista do DRF — um dicionário por linha, vazio nas
        que passaram — porque "a unidade está errada" numa ficha de oito
        ingredientes é inútil sem dizer em qual.
        """
        erros: list[dict[str, Any]] = []
        resultado: list[LinhaDaFicha] = []
        falhou = False
        for linha in linhas:
            produto = artigos[linha["ingredient"]]
            try:
                quantidade = em_unidade_pedida(
                    linha["quantity"], unidade=linha["unit"], produto=produto
                )
            except DRFValidationError as erro:
                erros.append(erro.detail if isinstance(erro.detail, dict) else {})
                falhou = True
                continue
            erros.append({})
            resultado.append(
                LinhaDaFicha(ingredient_id=linha["ingredient"], quantity=quantidade)
            )
        if falhou:
            raise DRFValidationError({"lines": erros})
        return resultado
