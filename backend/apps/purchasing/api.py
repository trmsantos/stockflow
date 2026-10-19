"""A porta do módulo `purchasing` (ARCHITECTURE.md §3).

Único ficheiro deste módulo que outro módulo pode importar. Hoje tem **dois**
consumidores — o `apps/agents/` e o `apps/demo/` — e expõe:

1. **As páginas de um documento como DTO congelado** (para `agents`);
2. **A forma de "o que o modelo leu"** (para `agents`);
3. **O porto da extração** (para `agents`);
4. **Funções de criação de documentos e receções** (para `demo`).

Reexportação e não definição: cada nome vive no ficheiro onde pertence
(`models.py`, `extracao.py`, `selectors.py`, `services.py`) e este é só a porta.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.utils import timezone

from apps.accounts import api as accounts_api
from apps.catalog import api as catalog_api
from apps.purchasing import selectors as _selectors
from apps.purchasing.extracao import (
    ConferenciaDeIva,
    DivergenciaDoCabecalho,
    FronteiraDaExtracao,
    LeituraDeDocumento,
    LinhaLida,
    PaginaDoDocumento,
    fronteira_da_extracao,
    ligar_fronteira_da_extracao,
)
from apps.purchasing.ficheiros import caminho_dentro_do_media
from apps.purchasing.models import EstadoDaLeitura
from apps.purchasing.selectors import compras_confirmadas as _compras_confirmadas
from apps.purchasing.selectors import pagina_por_id, paginas_do_documento

__all__ = [
    "DetalheDeRececao",
    "HistoricoDePrecos",
    "LinhaDeRececao",
    "PendenciasDaRececao",
    "PrecoPorFornecedorEMes",
    "ResumoDeRececao",
    "listar_rececoes",
    "precos_confirmados_por_artigo",
    "rececao_por_id",
    "ComprasPorArtigo",
    "ComprasPorFornecedor",
    "ComprasResumo",
    "ConferenciaDeIva",
    "DivergenciaDoCabecalho",
    "EstadoDaLeitura",
    "FronteiraDaExtracao",
    "LeituraDeDocumento",
    "LinhaLida",
    "PaginaDoDocumento",
    "TIPO_DA_IMAGEM_DA_PAGINA",
    "bytes_da_pagina",
    "fronteira_da_extracao",
    "ligar_fronteira_da_extracao",
    "paginas_do_documento",
    "compras_confirmadas",
    "criar_documento",
    "criar_receçao",
    "adicionar_linha_recepção",
]


#: O tipo real dos bytes que `bytes_da_pagina` devolve. É uma constante e não um
#: campo do DTO porque é verdade por construção: o normalizador da ADR 0021
#: grava **sempre** WebP, e a view da imagem serve `image/webp`. Quem monta um
#: `data:` URL para um modelo precisa do tipo, e esta é a linha que lho dá sem o
#: obrigar a adivinhar.
TIPO_DA_IMAGEM_DA_PAGINA = "image/webp"


def bytes_da_pagina(*, tenant_id: UUID, pagina_id: UUID) -> bytes:
    """Os bytes da imagem normalizada de uma página. **Uma página de cada vez.**

    É a função que a decisão 1 da ADR 0031 nomeia, e a razão de ela existir está
    escrita no DTO da página: *"é aqui que se decide se ele recebe bytes ou um
    caminho — e a resposta certa é bytes, para o `agents` não ter de conhecer o
    armazenamento do `purchasing`"*. O `PaginaDoDocumento` **não** ganha um campo
    de bytes: carregar a imagem em todas as listagens para a usar numa tarefa era
    pagar o ficheiro a cada `GET`.

    Devolve `b""` — e nunca levanta — nos quatro casos que de fora são o mesmo
    *"não há imagem desta página"*: a página não existe, é de outro
    estabelecimento, ainda não foi normalizada, ou os bytes desapareceram do
    disco. Quem chama trata o vazio, e a alternativa (uma excepção nova a
    atravessar a fronteira do módulo) alargava a porta para nada: o `agents` já
    tem de tratar o caso de não haver imagem nenhuma.
    """
    pagina = pagina_por_id(tenant_id=tenant_id, pagina_id=pagina_id)
    if pagina is None or not pagina.image_path:
        return b""
    try:
        caminho = caminho_dentro_do_media(pagina.image_path)
    except ValueError:
        return b""
    if not caminho.is_file():
        return b""
    return caminho.read_bytes()


@dataclass(frozen=True, kw_only=True, slots=True)
class DocumentoResumo:
    """Um documento como o demo o vê."""

    id: UUID
    origin: str


@dataclass(frozen=True, kw_only=True, slots=True)
class ReceçaoResumo:
    """Uma receção como o demo a vê."""

    id: UUID
    tenant_id: UUID
    supplier_id: UUID


@dataclass(frozen=True, kw_only=True, slots=True)
class ComprasPorFornecedor:
    """O total comprado a um fornecedor no período. `None` é "sem fornecedor"."""

    supplier_id: UUID | None
    supplier_name: str
    total_eur: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class ComprasPorArtigo:
    """O total comprado de um artigo no período. `None` é "linha sem artigo"."""

    product_id: UUID | None
    product_name: str
    total_eur: Decimal


@dataclass(frozen=True, kw_only=True, slots=True)
class ComprasResumo:
    """As compras confirmadas de um período, agregadas por `received_at` (ADR 0027).

    `total_eur` é **sem IVA**, líquido de desconto, com as notas de crédito a
    subtrair. `documentos_sem_preco` são as guias de remessa, que contam 0 e
    ficam contadas para a resposta não dizer "gastou 0 €".
    """

    total_eur: Decimal
    por_fornecedor: tuple[ComprasPorFornecedor, ...]
    por_artigo: tuple[ComprasPorArtigo, ...]
    documentos: int
    documentos_sem_preco: int
    linhas_sem_custo: int


def compras_confirmadas(
    *,
    tenant_id: UUID,
    desde: datetime,
    ate: datetime,
    supplier_id: UUID | None = None,
    product_id: UUID | None = None,
) -> ComprasResumo:
    """As compras confirmadas recebidas em `[desde, ate)`. Consumidor: `apps/agents`."""
    dados = _compras_confirmadas(
        tenant_id=tenant_id, desde=desde, ate=ate, supplier_id=supplier_id, product_id=product_id
    )
    return ComprasResumo(
        total_eur=dados["total_eur"],
        por_fornecedor=tuple(ComprasPorFornecedor(**f) for f in dados["por_fornecedor"]),
        por_artigo=tuple(ComprasPorArtigo(**p) for p in dados["por_artigo"]),
        documentos=dados["documentos"],
        documentos_sem_preco=dados["documentos_sem_preco"],
        linhas_sem_custo=dados["linhas_sem_custo"],
    )


def criar_documento(*, tenant_id: UUID) -> DocumentoResumo:
    """Cria um documento de fatura. Consumidor: `apps/demo`."""
    from apps.purchasing.models import InvoiceDocument, OrigemDoDocumento

    doc = InvoiceDocument.objects.create(tenant_id=tenant_id, source=OrigemDoDocumento.UPLOAD)
    return DocumentoResumo(id=doc.id, origin=doc.source)


def criar_receçao(
    *,
    tenant_id: UUID,
    supplier_id: UUID,
    location_id: UUID,
    document_id: UUID | None = None,
    status: str = "draft",
) -> ReceçaoResumo:
    """Cria uma receção com cabeçalho mínimo. Consumidor: `apps/demo`.

    Só por ids: fornecedor e localização são de outros módulos e a fronteira
    (import-linter) não deixa importar os modelos deles — a FK valida a existência.
    """
    from django.utils import timezone

    from apps.purchasing.models import InvoiceDocument, OrigemDoDocumento, Receipt

    if document_id is None:
        doc = InvoiceDocument.objects.create(tenant_id=tenant_id, source=OrigemDoDocumento.UPLOAD)
        document_id = doc.id

    receipt = Receipt.objects.create(
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        document_id=document_id,
        doc_type="FT",
        received_at=timezone.now(),
        location_id=location_id,
        confirmed_at=timezone.now() if status == "confirmed" else None,
    )
    return ReceçaoResumo(
        id=receipt.id, tenant_id=receipt.tenant_id, supplier_id=receipt.supplier_id
    )


def adicionar_linha_recepção(
    *,
    tenant_id: UUID,
    receipt_id: UUID,
    product_id: UUID,
    quantity: Decimal,
    unit_price: Decimal,
    description: str = "",
) -> UUID:
    """Adiciona uma linha a uma receção. Consumidor: `apps/demo`."""
    from apps.purchasing.models import Receipt, ReceiptLine

    receipt = Receipt.objects.get(id=receipt_id, tenant_id=tenant_id)

    linha = ReceiptLine.objects.create(
        tenant_id=tenant_id,
        receipt=receipt,
        position=receipt.lines.count(),
        description=description,
        invoice_unit="un",
        quantity_invoiced=quantity,
        unit_price=unit_price,
        quantity_received=quantity,
        location_id=receipt.location_id,
        kind="goods",
        product_id=product_id,
    )
    return linha.id


# ===========================================================================
# As receções e o histórico de preços pela porta (ADR 0028). DTOs congelados;
# **nenhum NIF sai por aqui** — nem do fornecedor nem do cliente. Uma resposta
# de assistente não é sítio para um número de contribuinte, e a forma de
# garantir isso é o DTO não ter onde o pôr.
# ===========================================================================
@dataclass(frozen=True, kw_only=True, slots=True)
class PendenciasDaRececao:
    """O que falta numa receção para poder ser confirmada, já derivado.

    Não é uma coluna: lê-se das linhas e do artigo de cada uma, como o
    `estado_derivado` de um documento. `temperaturas_em_falta` lista as classes
    de conservação **presentes** na receção cuja temperatura não foi registada
    (ADR 0022, decisão 5): uma receção só de ambiente nunca pede temperatura.
    """

    sem_artigo: int
    sem_lote: int
    sem_validade: int
    temperaturas_em_falta: tuple[str, ...]

    @property
    def total(self) -> int:
        return self.sem_artigo + self.sem_lote + self.sem_validade + len(
            self.temperaturas_em_falta
        )


@dataclass(frozen=True, kw_only=True, slots=True)
class ResumoDeRececao:
    """O cabeçalho de uma receção como a lista do assistente a mostra.

    `fornecedor_ligado` distingue o fornecedor **do catálogo** (FK, e portanto o
    que a memória de códigos e o histórico de preços usam) do nome que veio
    impresso no documento e que ninguém ligou ainda. São coisas diferentes e a
    resposta tem de as separar.
    """

    id: UUID
    supplier_id: UUID | None
    supplier_name: str
    fornecedor_ligado: bool
    doc_type: str
    doc_number: str
    doc_date: date | None
    received_at: datetime
    confirmed_at: datetime | None
    confirmed_by_name: str
    location_id: UUID | None
    location_name: str
    n_linhas: int
    #: Quantas linhas em cada `status` (`needs_review`/`confirmed`/`skipped`).
    linhas_por_estado: Mapping[str, int]
    pendencias: PendenciasDaRececao
    #: O total **do documento, com IVA**. Nunca se soma com `line_total`, que é
    #: sem IVA: são duas grandezas diferentes (ADR 0022).
    document_total_eur: Decimal | None


@dataclass(frozen=True, kw_only=True, slots=True)
class LinhaDeRececao:
    """Uma linha de uma receção, com o artigo e o que lhe falta."""

    id: UUID
    position: int
    description: str
    kind: str
    status: str
    product_id: UUID | None
    product_name: str
    sku: str
    base_unit: str
    display_unit: str
    display_factor: Decimal
    invoice_unit: str
    quantity_invoiced: Decimal | None
    quantity_received: Decimal | None
    base_per_invoice_unit: Decimal | None
    lot_code: str
    expires_at: date | None
    exige_lote: bool
    #: `use_by`, `best_before` ou `""`.
    expiry_kind: str
    conservation: str
    #: Dinheiro. Quem lê filtra pelo papel: um `staff` não vê nenhum destes.
    unit_price: Decimal | None
    discount_pct: Decimal | None
    vat_rate: Decimal | None
    line_total: Decimal | None


@dataclass(frozen=True, kw_only=True, slots=True)
class DetalheDeRececao:
    """Uma receção inteira: o cabeçalho e as linhas por posição."""

    resumo: ResumoDeRececao
    linhas: tuple[LinhaDeRececao, ...]
    truncado: bool


@dataclass(frozen=True, kw_only=True, slots=True)
class PrecoPorFornecedorEMes:
    """O que se pagou a um fornecedor por um artigo num mês de negócio.

    Os preços são **por unidade base** e sem IVA, líquidos de desconto. A média
    é **ponderada pela quantidade** e não a média dos preços: três sacos a 0,80
    e um a 1,20 dão 0,90 e não 1,00, e é 0,90 que custou.
    """

    supplier_id: UUID | None
    supplier_name: str
    #: O mês de negócio, `AAAA-MM`.
    mes: str
    n: int
    minimo: Decimal
    maximo: Decimal
    media: Decimal
    ultimo: Decimal
    ultimo_em: datetime


@dataclass(frozen=True, kw_only=True, slots=True)
class HistoricoDePrecos:
    """O histórico de preços de um artigo, por fornecedor e mês de negócio."""

    product_id: UUID
    desde: datetime
    ate: datetime
    base_unit: str
    display_unit: str
    display_factor: Decimal
    linhas: tuple[PrecoPorFornecedorEMes, ...]
    #: O último preço praticado e o anterior, para a variação do cabeçalho.
    ultimo: Decimal | None
    ultimo_em: datetime | None
    anterior: Decimal | None
    variacao_pct: Decimal | None
    #: Quantas notas de crédito/débito ficaram de fora. Ditas, não escondidas.
    notas_ignoradas: int
    truncado: bool


def _pendencias(linhas: Sequence[Any], produtos: Mapping[UUID, Any], receipt: Any):
    """O que falta a esta receção, derivado das linhas e dos artigos delas."""
    sem_artigo = sem_lote = sem_validade = 0
    classes = set()
    for linha in linhas:
        if linha.status == "skipped":
            continue
        produto = produtos.get(linha.product_id) if linha.product_id else None
        if linha.kind == "goods" and produto is None:
            sem_artigo += 1
            continue
        if produto is None:
            continue
        classes.add(produto.conservation)
        if produto.track_lots and not linha.lot_code:
            sem_lote += 1
        if produto.expiry_kind and linha.expires_at is None:
            sem_validade += 1
    em_falta = []
    if "chilled" in classes and receipt.chilled_temperature_c is None:
        em_falta.append("chilled")
    if "frozen" in classes and receipt.frozen_temperature_c is None:
        em_falta.append("frozen")
    return PendenciasDaRececao(
        sem_artigo=sem_artigo,
        sem_lote=sem_lote,
        sem_validade=sem_validade,
        temperaturas_em_falta=tuple(em_falta),
    )


def _resumo_de_rececao(receipt: Any, linhas: Sequence[Any], produtos: Mapping[UUID, Any]):
    """O `ResumoDeRececao` de uma receção já com as linhas e os artigos lidos."""
    por_estado: dict[str, int] = {}
    for linha in linhas:
        por_estado[linha.status] = por_estado.get(linha.status, 0) + 1
    return ResumoDeRececao(
        id=receipt.id,
        supplier_id=receipt.supplier_id,
        supplier_name=(
            receipt.supplier.name if receipt.supplier_id else receipt.supplier_name
        ),
        fornecedor_ligado=receipt.supplier_id is not None,
        doc_type=receipt.doc_type,
        doc_number=receipt.doc_number,
        doc_date=receipt.doc_date,
        received_at=receipt.received_at,
        confirmed_at=receipt.confirmed_at,
        confirmed_by_name=receipt.confirmed_by_name,
        location_id=receipt.location_id,
        location_name=receipt.location.name if receipt.location_id else "",
        n_linhas=len(linhas),
        linhas_por_estado=por_estado,
        pendencias=_pendencias(linhas, produtos, receipt),
        document_total_eur=receipt.document_total_eur,
    )


def _produtos_das_linhas(*, tenant_id: UUID, linhas: Sequence[Any]) -> Mapping[UUID, Any]:
    """Os artigos das linhas, numa query pela porta do catálogo."""
    ids = [linha.product_id for linha in linhas if linha.product_id is not None]
    if not ids:
        return {}
    return catalog_api.produtos_por_id(tenant_id=tenant_id, ids=ids)


def listar_rececoes(
    *,
    tenant_id: UUID,
    estado: str,
    limite: int = 20,
    agora: datetime | None = None,
) -> tuple[tuple[ResumoDeRececao, ...], bool]:
    """As receções de um estado, com as pendências derivadas, e se cortou.

    `por_rever` é `confirmed_at IS NULL`; `confirmadas` olha os últimos sete
    dias **de negócio**; `hoje` é desde o início do dia de negócio em curso.
    """
    desde: datetime | None = None
    if estado == "hoje":
        desde = _selectors.inicio_do_dia_de_negocio(tenant_id=tenant_id, agora=agora)
    elif estado == "confirmadas":
        desde = _selectors.inicio_do_dia_de_negocio(
            tenant_id=tenant_id, agora=agora
        ) - timedelta(days=_selectors.DIAS_DE_RECECOES_CONFIRMADAS)
    rececoes = _selectors.rececoes_por_estado(
        tenant_id=tenant_id, estado=estado, desde=desde, limite=limite
    )
    truncado = len(rececoes) > limite
    rececoes = rececoes[:limite]
    linhas_por_rececao = {
        receipt.id: _selectors.linhas_da_rececao(tenant_id=tenant_id, receipt_id=receipt.id)
        for receipt in rececoes
    }
    todas = [linha for linhas in linhas_por_rececao.values() for linha in linhas]
    produtos = _produtos_das_linhas(tenant_id=tenant_id, linhas=todas)
    return (
        tuple(
            _resumo_de_rececao(receipt, linhas_por_rececao[receipt.id], produtos)
            for receipt in rececoes
        ),
        truncado,
    )


def rececao_por_id(
    *, tenant_id: UUID, receipt_id: UUID, limite: int = 40
) -> DetalheDeRececao | None:
    """Uma receção com as linhas, ou `None` se não existir neste estabelecimento."""
    receipt = _selectors.rececao_do_ambito(tenant_id=tenant_id, receipt_id=receipt_id)
    if receipt is None:
        return None
    linhas = _selectors.linhas_da_rececao(tenant_id=tenant_id, receipt_id=receipt_id)
    produtos = _produtos_das_linhas(tenant_id=tenant_id, linhas=linhas)
    return DetalheDeRececao(
        resumo=_resumo_de_rececao(receipt, linhas, produtos),
        linhas=tuple(
            _linha_de_rececao(linha, produtos.get(linha.product_id) if linha.product_id else None)
            for linha in linhas[:limite]
        ),
        truncado=len(linhas) > limite,
    )


def _linha_de_rececao(linha: Any, produto: Any) -> LinhaDeRececao:
    """Uma `LinhaDeRececao` a partir da linha e do artigo dela (ou de nenhum)."""
    return LinhaDeRececao(
        id=linha.id,
        position=linha.position,
        description=linha.description,
        kind=linha.kind,
        status=linha.status,
        product_id=linha.product_id,
        product_name=produto.short_name if produto else "",
        sku=produto.sku if produto else "",
        base_unit=produto.base_unit if produto else "",
        display_unit=produto.display_unit if produto else "",
        display_factor=produto.display_factor if produto else Decimal("1"),
        invoice_unit=linha.invoice_unit,
        quantity_invoiced=linha.quantity_invoiced,
        quantity_received=linha.quantity_received,
        base_per_invoice_unit=linha.base_per_invoice_unit,
        lot_code=linha.lot_code,
        expires_at=linha.expires_at,
        exige_lote=bool(produto.track_lots) if produto else False,
        expiry_kind=(produto.expiry_kind or "") if produto else "",
        conservation=produto.conservation if produto else "",
        unit_price=linha.unit_price,
        discount_pct=linha.discount_pct,
        vat_rate=linha.vat_rate,
        line_total=linha.line_total,
    )


def _mes_de_negocio(instante: datetime, *, inicio_do_dia: time) -> str:
    """O mês de negócio de um instante, `AAAA-MM`.

    O mês de negócio é `[dia 1 às <inicio>, dia 1 do mês seguinte às <inicio>)`
    (ADR 0013, decisão 8): uma entrada à 01:30 do dia 1 pertence ao mês
    anterior, que é o que faz `Σ(meses)` dar o ano.
    """
    local = timezone.localtime(instante)
    dia = local.date() if local.time() >= inicio_do_dia else local.date() - timedelta(days=1)
    return f"{dia.year:04d}-{dia.month:02d}"


def precos_confirmados_por_artigo(
    *,
    tenant_id: UUID,
    product_id: UUID,
    meses: int = 6,
    agora: datetime | None = None,
) -> HistoricoDePrecos | None:
    """O que se pagou por um artigo, por fornecedor e mês de negócio (ADR 0028).

    O preço de uma linha é `line_total / (quantity_invoiced ×
    base_per_invoice_unit)`, isto é, euros por unidade **base** — sem IVA e
    líquido de desconto, que é o que uma fatura portuguesa imprime por linha.
    Nunca se divide pela quantidade **recebida**: numa receção parcial o que se
    pagou foi o que veio na fatura.

    A média do mês é ponderada pela quantidade (`Σ total / Σ quantidade base`)
    e não a média aritmética dos preços. As guias de remessa não entram (não
    trazem preço) e as notas de crédito e de débito também não — são correcções
    a um preço já praticado —, mas ficam **contadas** em `notas_ignoradas`.

    `None` quando o artigo não existe no catálogo deste estabelecimento.
    """
    produtos = catalog_api.produtos_por_id(tenant_id=tenant_id, ids=[product_id])
    produto = produtos.get(product_id)
    if produto is None:
        return None
    meses = max(1, min(meses, _selectors.MESES_MAXIMOS_DE_PRECOS))
    inicio_do_dia = accounts_api.inicio_do_dia_de_negocio(tenant_id=tenant_id)
    ate = _selectors.inicio_do_dia_de_negocio(tenant_id=tenant_id, agora=agora) + timedelta(days=1)
    desde = ate - timedelta(days=31 * meses)
    linhas = _selectors.linhas_com_preco_confirmado(
        tenant_id=tenant_id, product_id=product_id, desde=desde, ate=ate
    )

    notas = 0
    baldes: dict[tuple[UUID | None, str], dict[str, Any]] = {}
    precos_por_instante: list[tuple[datetime, Decimal]] = []
    for linha in linhas:
        if linha["receipt__doc_type"] in _selectors.DOC_TIPOS_DE_NOTA:
            notas += 1
            continue
        quantidade = linha["quantity_invoiced"] * linha["base_per_invoice_unit"]
        if quantidade <= 0:
            continue
        total = linha["line_total"]
        preco = total / quantidade
        quando = linha["receipt__received_at"]
        precos_por_instante.append((quando, preco))
        chave = (
            linha["receipt__supplier_id"],
            _mes_de_negocio(quando, inicio_do_dia=inicio_do_dia),
        )
        balde = baldes.setdefault(
            chave,
            {
                "supplier_id": linha["receipt__supplier_id"],
                "supplier_name": (
                    linha["receipt__supplier__name"] or linha["receipt__supplier_name"]
                ),
                "mes": chave[1],
                "n": 0,
                "minimo": preco,
                "maximo": preco,
                "total": Decimal("0"),
                "quantidade": Decimal("0"),
                "ultimo": preco,
                "ultimo_em": quando,
            },
        )
        balde["n"] += 1
        balde["minimo"] = min(balde["minimo"], preco)
        balde["maximo"] = max(balde["maximo"], preco)
        balde["total"] += total
        balde["quantidade"] += quantidade
        if quando >= balde["ultimo_em"]:
            balde["ultimo"] = preco
            balde["ultimo_em"] = quando

    precos_por_instante.sort(key=lambda par: par[0])
    ultimo = precos_por_instante[-1][1] if precos_por_instante else None
    ultimo_em = precos_por_instante[-1][0] if precos_por_instante else None
    anterior = precos_por_instante[-2][1] if len(precos_por_instante) > 1 else None
    variacao = None
    if ultimo is not None and anterior is not None and anterior > 0:
        variacao = ((ultimo - anterior) / anterior) * Decimal("100")

    ordenados = sorted(baldes.values(), key=lambda b: (b["mes"], b["supplier_name"]))
    return HistoricoDePrecos(
        product_id=product_id,
        desde=desde,
        ate=ate,
        base_unit=produto.base_unit,
        display_unit=produto.display_unit,
        display_factor=produto.display_factor,
        linhas=tuple(
            PrecoPorFornecedorEMes(
                supplier_id=balde["supplier_id"],
                supplier_name=balde["supplier_name"],
                mes=balde["mes"],
                n=balde["n"],
                minimo=balde["minimo"],
                maximo=balde["maximo"],
                media=balde["total"] / balde["quantidade"],
                ultimo=balde["ultimo"],
                ultimo_em=balde["ultimo_em"],
            )
            for balde in ordenados
        ),
        ultimo=ultimo,
        ultimo_em=ultimo_em,
        anterior=anterior,
        variacao_pct=variacao,
        notas_ignoradas=notas,
        truncado=len(linhas) >= 500,
    )
