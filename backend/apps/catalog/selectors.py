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

from django.db.models import Q, QuerySet

from apps.catalog.models import Product, ProductPackaging, Supplier, SupplierProductCode

__all__ = [
    "codigos_do_fornecedor",
    "codigos_do_produto",
    "embalagens_do_ambito",
    "embalagens_do_produto",
    "fornecedores_do_ambito",
    "listar_fornecedores",
    "listar_produtos",
    "procurar_fornecedores",
    "procurar_produtos",
    "produtos_do_ambito",
]

#: Os limites da procura do assistente (ADR 0027, decisão 5): dez por omissão,
#: vinte no máximo. O modelo pede mais quando precisa, e um resultado de cem
#: linhas não cabe nos 8 KB de uma resposta de tool.
LIMITE_DA_PROCURA = 10
LIMITE_MAXIMO_DA_PROCURA = 20


def _tokens(q: str) -> list[str]:
    """As palavras da pergunta, separadas por espaço. Sem `unaccent` nesta fatia."""
    return [token for token in q.split() if token]


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


def procurar_produtos(
    *, tenant_id: UUID, q: str, limite: int = LIMITE_DA_PROCURA
) -> list[Product]:
    """A procura do assistente: cada palavra casa no nome curto **ou** no SKU.

    Tokens separados por espaço em **AND** — "farinha t65" encontra "Farinha T65"
    e não encontra "Farinha T55" — e cada token é `icontains` sobre o nome ou
    sobre o SKU, porque é por qualquer dos dois que o staff nomeia o artigo. Só
    caixa, sem acentos: `unaccent` é uma extensão do Postgres e uma decisão
    própria (ADR 0027, decisão 5).

    Activos primeiro, e os inactivos **marcados e não escondidos**: um artigo
    desactivado continua a ter histórico, e a resposta certa a "quanto tenho de
    X" sobre um artigo inactivo é "está inactivo", não "não existe".
    """
    artigos = produtos_do_ambito(tenant_id=tenant_id)
    for token in _tokens(q):
        artigos = artigos.filter(Q(short_name__icontains=token) | Q(sku__icontains=token))
    limite = max(1, min(limite, LIMITE_MAXIMO_DA_PROCURA))
    return list(artigos.order_by("-is_active", "short_name", "id")[:limite])


def procurar_fornecedores(
    *, tenant_id: UUID, q: str, limite: int = LIMITE_DA_PROCURA
) -> list[Supplier]:
    """A procura de fornecedores do assistente: nome por tokens, NIF exacto.

    O NIF é chave e não texto: nove dígitos casam só com o NIF inteiro, porque
    "5000" a casar com metade de um NIF era um fornecedor errado com aspecto de
    certo.
    """
    fornecedores = fornecedores_do_ambito(tenant_id=tenant_id)
    termo = q.strip()
    if termo.isdigit():
        fornecedores = fornecedores.filter(nif=termo)
    else:
        for token in _tokens(termo):
            fornecedores = fornecedores.filter(name__icontains=token)
    limite = max(1, min(limite, LIMITE_MAXIMO_DA_PROCURA))
    return list(fornecedores.order_by("-is_active", "name", "id")[:limite])


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


def codigos_do_produto(*, tenant_id: UUID, product_id: UUID) -> QuerySet[SupplierProductCode]:
    """A memória **pelo artigo**: que fornecedores o nomeiam e com que código.

    O irmão do `codigos_do_fornecedor`, do outro lado da mesma tabela: aquele
    responde "que artigo é este código da Makro", este responde "como é que os
    meus fornecedores chamam a este artigo", que é o que a ficha do artigo
    mostra. O `select_related("supplier")` serve o nome do fornecedor por linha.
    """
    return (
        SupplierProductCode.objects.filter(tenant_id=tenant_id, product_id=product_id)
        .select_related("supplier")
        .order_by("supplier__name", "code")
    )
