"""Queries de leitura dos documentos. Nenhuma escreve.

Todas recebem `tenant_id` e filtram por ele. Não é redundância com a política de
RLS: são as **duas** redes que o `SECURITY.md` §1 exige lado a lado, e a de cima
é esta. A consequência visível é que o `id` de um documento de outro
estabelecimento dá **404 e não 403** — a linha não é legível, logo não há objecto
sobre o qual negar, e um 403 confirmaria que aquele documento existe.

O que está aqui e não no `views.py`: a **composição** do documento com a última
leitura do modelo, que atravessa o porto do `extracao.py`. Fica num sítio só
porque a listagem e o detalhe precisam exactamente da mesma coisa, e porque é o
ponto onde o N+1 se evita — as leituras vêm em lote, uma chamada por página de
resultados.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.db.models import Count, Prefetch, QuerySet

from apps.purchasing.extracao import (
    LeituraDeDocumento,
    PaginaDoDocumento,
    fronteira_da_extracao,
)
from apps.purchasing.models import (
    JANELA_DO_SLOT,
    PAGINAS_POR_DOCUMENTO,
    DocumentFile,
    DocumentPage,
    InvoiceDocument,
    estado_do_documento,
)

__all__ = [
    "DocumentoCompleto",
    "com_paginas",
    "compor",
    "compor_muitos",
    "documentos_do_ambito",
    "documentos_visiveis",
    "pagina_por_posicao",
    "paginas_do_documento",
    "slots_expirados",
]


@dataclass(frozen=True, kw_only=True, slots=True)
class DocumentoCompleto:
    """O documento como o `DocumentoOut` o serve: a linha mais o que se deriva.

    Não é um DTO de fronteira — não atravessa módulo nenhum e por isso não está
    no `api.py`. É a forma que o serializer lê, e existe por duas razões: para a
    derivação do estado não acontecer dentro de um serializer (onde ninguém a
    testa sem HTTP), e para quase todos os campos do `DocumentoOut` serem um
    `source=` sobre isto em vez de um `SerializerMethodField` — o que mantém o
    `schema.yml` tipado sem um `@extend_schema_field` por campo. Sobram dois
    métodos (o `image_url` de uma página e o `receipt`), e os dois têm o tipo
    declarado.

    `paginas` e `ficheiros` vêm já ordenados e já carregados: ordenar aqui é o
    que impede uma lista de páginas servida na ordem em que o Postgres as
    devolveu, que não é ordem nenhuma.
    """

    documento: InvoiceDocument
    estado: str
    leitura: LeituraDeDocumento | None
    paginas: list[DocumentPage]
    ficheiros: list[DocumentFile]
    page_count: int
    page_limit: int
    expires_at: datetime
    #: A receção que este documento produziu. **Sempre `None` nesta fatia**: o
    #: `purchasing_receipt` nasce na fatia 2. Está aqui (e não como um método no
    #: serializer) para o `types.ts` prometer `receipt: string | null` — um campo
    #: de método sai **opcional** no componente de resposta, e um tipo opcional
    #: obriga o cliente a tratar um caso que o servidor nunca produz.
    receipt: UUID | None = None


#: As duas colecções de um documento, pré-carregadas **e ordenadas**. O
#: `Prefetch` explícito e não um `prefetch_related("pages")` simples: nenhum dos
#: dois modelos tem `ordering` no `Meta` (o `TenantModel` só traz o índice), logo
#: sem isto a ordem das páginas de uma fatura de duas folhas era a ordem em que o
#: Postgres as devolvesse — que não é ordem nenhuma, e numa fatura é a diferença
#: entre a primeira e a segunda folha.
_COLECCOES = (
    Prefetch("files", queryset=DocumentFile.objects.order_by("position")),
    Prefetch("pages", queryset=DocumentPage.objects.order_by("position")),
)


def documentos_do_ambito(*, tenant_id: UUID) -> QuerySet[InvoiceDocument]:
    """Todos os documentos do estabelecimento, incluindo vazios e descartados.

    É a base do `get_queryset` da view, e portanto a base do `get_object()`: o
    `GET /documents/<id>` é o alvo do polling (ADR 0020, decisão 3) e tem de
    servir um slot **ainda sem páginas** — é precisamente esse o estado que o
    desktop está a sondar enquanto espera pela fotografia.
    """
    return InvoiceDocument.objects.filter(tenant_id=tenant_id)


def documentos_visiveis(*, tenant_id: UUID) -> QuerySet[InvoiceDocument]:
    """Os documentos que a lista do Receber mostra, mais recentes primeiro.

    Duas exclusões, e as duas são decisões e não filtros de conveniência:

    * **zero páginas não aparece.** *"Um documento com zero páginas nunca aparece
      na lista do Receber"* (ADR 0020, decisão 2) — um slot aberto e nunca usado é
      uma intenção, não um documento, e aparecer na lista fazia o ecrã encher-se
      de linhas que ninguém criou de propósito;
    * **descartado não aparece.** Descartar é dizer "isto não interessa"; a linha
      fica para o rasto e para o `GET` directo, não para a lista.

    `prefetch_related` nos ficheiros e nas páginas porque o `DocumentoOut` serve
    os dois por documento: sem ele são duas queries por linha, que é o N+1 que o
    `django-reviewer` procura. Ordem explícita e não a herdada, porque uma
    listagem paginada sem `ORDER BY` estável devolve páginas que se repetem.
    """
    return (
        documentos_do_ambito(tenant_id=tenant_id)
        .filter(discarded_at__isnull=True)
        .annotate(quantas_paginas=Count("pages"))
        .filter(quantas_paginas__gt=0)
        .prefetch_related(*_COLECCOES)
        .order_by("-created_at", "id")
    )


def slots_expirados(*, tenant_id: UUID, limite: datetime) -> QuerySet[InvoiceDocument]:
    """Os slots que nunca receberam página e já passaram do relógio.

    É o que a tarefa de limpeza apaga. `limite` é um instante e vem de quem
    chama, não de um `timezone.now()` aqui dentro: um selector que leia o relógio
    é um selector que não se testa.
    """
    return documentos_do_ambito(tenant_id=tenant_id).filter(
        created_at__lt=limite,
        discarded_at__isnull=True,
    ).annotate(quantas_paginas=Count("pages")).filter(quantas_paginas=0)


def paginas_do_documento(
    *, tenant_id: UUID, documento_id: UUID
) -> tuple[PaginaDoDocumento, ...]:
    """As páginas de um documento, ordenadas, como DTO congelado.

    É o que o `api.py` reexporta para o `agents` (ADR 0020, decisão 6: *"dá-lhe
    páginas como DTO congelado"*). Tupla vazia para um documento que não existe
    **ou** que é de outro estabelecimento: a política devolve zero linhas e de
    fora as duas coisas são indistinguíveis, que é a propriedade que se quer.
    """
    linhas = DocumentPage.objects.filter(
        tenant_id=tenant_id, document_id=documento_id
    ).order_by("position")
    return tuple(
        PaginaDoDocumento(
            id=pagina.id,
            position=pagina.position,
            file_page_number=pagina.file_page_number,
            imagem=pagina.image_path,
            qr_payload=pagina.qr_payload,
            normalized=pagina.normalized_at is not None,
        )
        for pagina in linhas
    )


def pagina_por_posicao(
    *, tenant_id: UUID, documento_id: UUID, posicao: int
) -> DocumentPage | None:
    """A página numa posição, ou `None`. Serve o endpoint da imagem.

    `None` cobre as três situações que têm de ser indistinguíveis de fora: o
    documento não existe, é de outro estabelecimento, ou não tem aquela página.
    """
    return (
        DocumentPage.objects.filter(
            tenant_id=tenant_id, document_id=documento_id, position=posicao
        )
        .select_related("file")
        .first()
    )


# ---------------------------------------------------------------------------
# Composição com a extração, que atravessa o porto
# ---------------------------------------------------------------------------
def _leituras(
    *, tenant_id: UUID, documento_ids: Sequence[UUID]
) -> Mapping[UUID, LeituraDeDocumento]:
    """As últimas leituras, pelo porto, ou vazio se não houver adaptador ligado."""
    fronteira = fronteira_da_extracao()
    if fronteira is None or not documento_ids:
        return {}
    return fronteira.leituras(tenant_id=tenant_id, documento_ids=documento_ids)


def compor_muitos(
    *, tenant_id: UUID, documentos: Sequence[InvoiceDocument]
) -> list[DocumentoCompleto]:
    """Junta cada documento à sua última leitura e deriva o estado. Em lote."""
    leituras = _leituras(
        tenant_id=tenant_id, documento_ids=[documento.id for documento in documentos]
    )
    compostos: list[DocumentoCompleto] = []
    for documento in documentos:
        leitura = leituras.get(documento.id)
        paginas = list(documento.pages.all())
        compostos.append(
            DocumentoCompleto(
                documento=documento,
                estado=estado_do_documento(
                    discarded_at=documento.discarded_at,
                    created_at=documento.created_at,
                    page_count=len(paginas),
                    estado_da_leitura=None if leitura is None else leitura.state,
                    leitura_desde=None if leitura is None else leitura.desde,
                ),
                leitura=leitura,
                paginas=paginas,
                ficheiros=list(documento.files.all()),
                page_count=len(paginas),
                page_limit=PAGINAS_POR_DOCUMENTO,
                expires_at=documento.created_at + JANELA_DO_SLOT,
                receipt=None,
            )
        )
    return compostos


def compor(*, tenant_id: UUID, documento: InvoiceDocument) -> DocumentoCompleto:
    """O mesmo, para um documento só. A view do detalhe e as de escrita usam-na."""
    return compor_muitos(tenant_id=tenant_id, documentos=[documento])[0]


def com_paginas(*, tenant_id: UUID, documento_id: UUID) -> InvoiceDocument | None:
    """O documento com ficheiros e páginas já carregados, ou `None`.

    Usado depois de uma escrita: o serviço devolve a linha, e servir o
    `DocumentoOut` a partir dela faria uma query por colecção. Com o prefetch são
    duas, sempre.
    """
    return (
        documentos_do_ambito(tenant_id=tenant_id)
        .filter(pk=documento_id)
        .prefetch_related(*_COLECCOES)
        .first()
    )
