"""Texto ausente é `''` e nunca `NULL` nos quatro campos do `inventory` que o permitiam.

`StockMovement.reason`, `StockMovement.reason_detail`, `StockMovement.reference` e
`StockCountLine.zone` eram `null=True, blank=True` até à migração
`inventory.0007_texto_sem_null_no_ledger_e_nas_contagens`. Dois valores a significar "nada"
obrigam cada leitor a tratar os dois, e foi assim que nasceram os `or ""` e `or None` do
`reporting`, do `inventory.api` e do `agents.tools`.

Este ficheiro afirma as duas metades da convenção, e afirma-as **na base de dados** e não só
no modelo: que ausência se escreve `''` quando ninguém diz nada, e que `NULL` é recusado pelo
`NOT NULL` da coluna mesmo que alguém o force pelo ORM. A segunda metade é a que importa —
um `default=""` sozinho não impede um `None` explícito de chegar à coluna, e era exatamente
isso que o `reason=None` do `purchasing` e os `reference=None` do `recipes` faziam.

Afirma também que o índice parcial de `reference` **continua parcial**: com a coluna
`NOT NULL`, o predicado antigo (`WHERE reference IS NOT NULL`) passaria a ser verdadeiro para
todas as linhas e o índice virava total sem ninguém dar por isso.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.accounts.services import criar_tenant
from apps.catalog.models import Product, UnidadeBase
from apps.inventory.models import (
    Location,
    StockCount,
    StockCountLine,
    StockMovement,
)
from apps.shared.db import tenant_scope

#: Os três campos de texto opcionais do ledger. A lista é explícita e não lida do
#: `_meta`: se um quarto aparecer, quem o escrever tem de vir aqui dizê-lo.
CAMPOS_DO_MOVIMENTO = ("reason", "reason_detail", "reference")

#: O índice parcial de deduplicação por documento.
INDICE_DE_REFERENCIA = "inv_stockmv_tenant_ref_idx"


@pytest.fixture
def cenario(db: None) -> Iterator[SimpleNamespace]:
    """Um tenant com artigo, localização e contagem, cedido com o âmbito aberto."""
    tenant = criar_tenant(name="Texto Sem Null")
    with tenant_scope(tenant.id):
        produto = Product.objects.create(
            tenant=tenant,
            short_name="Farinha T65",
            base_unit=UnidadeBase.GRAMA,
            display_unit="kg",
            display_factor=Decimal("1000"),
            track_lots=False,
            expiry_kind="",
            is_active=True,
        )
        local = Location.objects.create(tenant=tenant, name="Despensa", position=0)
        contagem = StockCount.objects.create(tenant=tenant, location=local, status="open")
        yield SimpleNamespace(tenant=tenant, produto=produto, local=local, contagem=contagem)


def _movimento(cenario: SimpleNamespace, **extra: object) -> StockMovement:
    """Um movimento mínimo: só o que a tabela exige, mais o que o teste quiser."""
    return StockMovement.objects.create(
        tenant=cenario.tenant,
        product=cenario.produto,
        location=cenario.local,
        movement_type="receipt",
        quantity=Decimal("1.000"),
        unit_cost=Decimal("1.000000"),
        cost_is_estimate=False,
        occurred_at=timezone.now(),
        created_by_name="teste",
        **extra,
    )


def _linha_de_contagem(cenario: SimpleNamespace, **extra: object) -> StockCountLine:
    """Uma linha de contagem mínima."""
    return StockCountLine.objects.create(
        tenant=cenario.tenant,
        stock_count=cenario.contagem,
        product=cenario.produto,
        quantity_expected=Decimal("0.000"),
        **extra,
    )


def test_o_default_dos_quatro_campos_e_string_vazia() -> None:
    """Sem tocar na base de dados: o modelo não tem `None` em campo de texto."""
    movimento = StockMovement()
    linha = StockCountLine()

    assert [getattr(movimento, campo) for campo in CAMPOS_DO_MOVIMENTO] == ["", "", ""]
    assert linha.zone == ""


def test_movimento_sem_texto_fica_com_string_vazia_na_base(
    cenario: SimpleNamespace,
) -> None:
    """Quem não diz nada escreve `''`, e é `''` que volta da base de dados."""
    movimento = _movimento(cenario)
    movimento.refresh_from_db()

    assert [getattr(movimento, campo) for campo in CAMPOS_DO_MOVIMENTO] == ["", "", ""]


@pytest.mark.parametrize("campo", CAMPOS_DO_MOVIMENTO)
def test_movimento_recusa_null_no_texto(cenario: SimpleNamespace, campo: str) -> None:
    """Um `None` explícito morre no `NOT NULL` da coluna, não passa a `''` em silêncio."""
    with pytest.raises(IntegrityError), transaction.atomic():
        _movimento(cenario, **{campo: None})


def test_linha_de_contagem_sem_zona_fica_com_string_vazia(
    cenario: SimpleNamespace,
) -> None:
    """A linha sem zona guarda `''`."""
    linha = _linha_de_contagem(cenario)
    linha.refresh_from_db()

    assert linha.zone == ""


def test_linha_de_contagem_recusa_zona_null(cenario: SimpleNamespace) -> None:
    """E `zone=None` é recusado pela coluna."""
    with pytest.raises(IntegrityError), transaction.atomic():
        _linha_de_contagem(cenario, zone=None)


def test_o_indice_de_referencia_continua_parcial(cenario: SimpleNamespace) -> None:
    """O predicado passou de `IS NOT NULL` para `<> ''`, e continua a haver predicado.

    Sem esta asserção, o índice parcial virava total na migração que tirou o `NULL` da
    coluna — o `WHERE reference IS NOT NULL` passaria a ser verdadeiro para toda a linha,
    e nada falharia.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = %s",
            [INDICE_DE_REFERENCIA],
        )
        linha = cursor.fetchone()

    assert linha is not None, f"o índice {INDICE_DE_REFERENCIA} não existe"
    definicao = linha[0]
    assert " WHERE " in definicao, f"o índice deixou de ser parcial: {definicao}"
    assert "IS NOT NULL" not in definicao, (
        f"o predicado ainda fala de NULL numa coluna NOT NULL: {definicao}"
    )
