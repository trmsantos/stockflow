"""Queries de leitura do catálogo. Nenhuma escreve.

Todas recebem `tenant_id` e filtram por ele. Não é redundância com a política de
RLS: são as **duas** redes que o `SECURITY.md` §1 exige lado a lado, e a de cima
é esta. A consequência visível é que o `id` de um artigo de outro estabelecimento
dá **404 e não 403** — a linha não é legível, logo não há objecto sobre o qual
negar, e um 403 confirmaria que aquele artigo existe.

As listagens têm `ORDER BY` estável (o nome e depois o `id`): uma listagem
paginada sem ordem estável devolve páginas que se repetem. E têm `q` e `active`
aqui e não na view, porque é aqui que a forma da query se testa sem HTTP.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from django.db.models import QuerySet

from apps.catalog.models import Product, ProductPackaging, Supplier, SupplierProductCode

__all__ = [
    "codigos_do_fornecedor",
    "embalagens_do_ambito",
    "embalagens_do_produto",
    "fornecedores_do_ambito",
    "listar_fornecedores",
    "listar_produtos",
    "produtos_do_ambito",
]


def produtos_do_ambito(*, tenant_id: UUID) -> QuerySet[Product]:
    """Todos os artigos do estabelecimento, activos ou não. A base do `get_object()`."""
    return Product.objects.filter(tenant_id=tenant_id)


def listar_produtos(
    *, tenant_id: UUID, q: str = "", active: bool | None = None
) -> QuerySet[Product]:
    """A lista do `GET /products`: por `short_name`, com os dois filtros do contrato.

    `active=None` traz todos — é o que o seletor de artigo da revisão quer quando
    precisa de mostrar um artigo desactivado que uma linha antiga ainda aponta.
    `q` é `icontains` sobre o nome curto: é "como o staff lhe chama", e é por
    isso que se procura por aí e não pela descrição da fatura.
    """
    artigos = produtos_do_ambito(tenant_id=tenant_id)
    if q:
        artigos = artigos.filter(short_name__icontains=q)
    if active is not None:
        artigos = artigos.filter(is_active=active)
    return artigos.order_by("short_name", "id")


def embalagens_do_ambito(*, tenant_id: UUID) -> QuerySet[ProductPackaging]:
    """Todas as embalagens do estabelecimento, com o artigo carregado.

    `select_related("product")` porque o `EmbalagemOut` serve a `base_unit` do
    artigo em cada linha — sem ele era uma query por embalagem.
    """
    return ProductPackaging.objects.filter(tenant_id=tenant_id).select_related("product")


def embalagens_do_produto(*, tenant_id: UUID, product_id: UUID) -> QuerySet[ProductPackaging]:
    """As embalagens de um artigo, na ordem em que foram criadas."""
    return embalagens_do_ambito(tenant_id=tenant_id).filter(product_id=product_id).order_by(
        "created_at", "id"
    )


def fornecedores_do_ambito(*, tenant_id: UUID) -> QuerySet[Supplier]:
    """Todos os fornecedores do estabelecimento. A base do `get_object()`."""
    return Supplier.objects.filter(tenant_id=tenant_id)


def listar_fornecedores(
    *, tenant_id: UUID, q: str = "", active: bool | None = None
) -> QuerySet[Supplier]:
    """A lista do `GET /suppliers`: por nome, com `q` e `active`."""
    fornecedores = fornecedores_do_ambito(tenant_id=tenant_id)
    if q:
        fornecedores = fornecedores.filter(name__icontains=q)
    if active is not None:
        fornecedores = fornecedores.filter(is_active=active)
    return fornecedores.order_by("name", "id")


def codigos_do_fornecedor(
    *, tenant_id: UUID, supplier_id: UUID, codes: Iterable[str] | None = None
) -> QuerySet[SupplierProductCode]:
    """A memória de um fornecedor, com artigo e embalagem carregados.

    `codes` restringe à lista pedida — é o caminho do `correspondencias` do
    `api.py`, que recebe os códigos de uma receção inteira e faz **uma** query.
    Sem `codes`, é a lista do `GET /suppliers/<id>/product-codes`.

    O `select_related` dos dois é para o `CodigoDeFornecedorOut`, que serve o
    nome do artigo e o rótulo da embalagem por linha. É travessia **dentro** do
    módulo, que é a única permitida: fora dele os nomes vêm pelo `api.py`.
    """
    linhas = SupplierProductCode.objects.filter(
        tenant_id=tenant_id, supplier_id=supplier_id
    ).select_related("product", "packaging")
    if codes is not None:
        linhas = linhas.filter(code__in=list(codes))
    return linhas.order_by("code", "id")
