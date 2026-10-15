"""Testes para problemas 1-5 (SKU, lote/validade, track_lots, contagem).

## `tenant_uuid` abre o âmbito e mantém-no aberto

Os testes criam linhas à mão (`Location.objects.create`,
`StockCount.objects.create`) e chamam serviços que leem tabelas com política
de RLS; o guarda do `tests/conftest.py` recusa qualquer DML fora de
`tenant_scope`. Em vez de cada teste abrir o seu bloco, a fixture cria o
tenant pelo serviço, concede a pertença dentro do âmbito — a forma de
`tests/test_stock_panel.py` — e **cede o UUID com o âmbito ainda aberto**,
pelo que o teste inteiro corre dentro dele. O `tenant_ctx` é o próprio
`tenant_scope`, reentrante para o mesmo tenant (um savepoint).
"""

from collections.abc import Iterator
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import Papel, User
from apps.accounts.services import conceder_pertenca, criar_tenant
from apps.catalog.models import UnidadeBase
from apps.catalog.services import actualizar_produto, criar_produto
from apps.inventory.count_services import (
    abrir_contagem,
    adicionar_linha_contagem,
    fechar_contagem,
    resumo_contagem,
)
from apps.inventory.models import Location, StockCount, StockLevel, StockMovement
from apps.inventory.services import MovementDTO, record_movements
from apps.purchasing.serializers import RevisaoDeLinhaInSerializer
from apps.shared.db import tenant_scope

CREDENCIAL = "problemas-teste-123"


@pytest.fixture
def tenant_uuid(db: None) -> Iterator[UUID]:
    """O UUID de um tenant com dono, cedido com o âmbito dele aberto."""
    tenant = criar_tenant(name="Problemas Teste")
    with tenant_scope(tenant.id):
        user = User.objects.create_user("dono@problemas.pt", CREDENCIAL)
        conceder_pertenca(
            user=user, tenant_id=tenant.id, role=Papel.OWNER, display_name="Dono"
        )
        yield tenant.id


@pytest.fixture
def tenant_ctx():
    """O `tenant_scope`, para os testes que querem o bloco explícito."""
    return tenant_scope


def _contexto_do_pedido(tenant_id: UUID) -> dict[str, object]:
    """O que o `RevisaoDeLinhaInSerializer` lê do pedido: `request.tenant.id`.

    A regra do lote obrigatório procura o artigo no estabelecimento do pedido,
    e sem pedido no contexto não tem onde o procurar — não valida. Nos testes o
    pedido é este objecto mínimo, com o mesmo atributo que a view lhe dá.
    """
    return {"request": SimpleNamespace(tenant=SimpleNamespace(id=tenant_id))}


def _receber(*, tenant_id: UUID, product_id: UUID, location_id: UUID, quantidade: Decimal) -> None:
    """Uma entrada no ledger, sem lote, pelo serviço — nunca por `StockLevel`."""
    record_movements(
        tenant_id=tenant_id,
        movements=[
            MovementDTO(
                product_id=product_id,
                location_id=location_id,
                lot_id=None,
                quantity=quantidade,
                unit_cost=Decimal("2.00"),
                cost_is_estimate=False,
                movement_type="receipt",
                occurred_at=timezone.now(),
                created_by_id=None,
                created_by_name="teste",
            )
        ],
    )


@pytest.mark.django_db
class TestSKU:
    """Problema 3: SKU único por tenant."""

    def test_product_sku_created(self, tenant_uuid):
        """Produto criado com SKU."""
        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Manteiga",
            base_unit=UnidadeBase.GRAMA,
            display_unit="kg",
            display_factor=Decimal("1000"),
            sku="MANTEIGA001",
        )
        assert produto.sku == "MANTEIGA001"

    def test_product_sku_defaults_to_short_name(self, tenant_uuid):
        """SKU padrão é short_name se não fornecido."""
        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Leite",
            base_unit=UnidadeBase.MILILITRO,
            display_unit="l",
            display_factor=Decimal("1000"),
        )
        assert produto.sku == "Leite"

    def test_product_sku_duplicated_rejected(self, tenant_uuid):
        """SKU duplicado é rejeitado."""
        criar_produto(
            tenant_id=tenant_uuid,
            short_name="Queijo A",
            base_unit=UnidadeBase.GRAMA,
            display_unit="kg",
            display_factor=Decimal("1000"),
            sku="QUEIJO001",
        )
        with pytest.raises(ValidationError) as exc:
            criar_produto(
                tenant_id=tenant_uuid,
                short_name="Queijo B",
                base_unit=UnidadeBase.GRAMA,
                display_unit="kg",
                display_factor=Decimal("1000"),
                sku="QUEIJO001",  # Duplicado
            )
        assert "sku" in exc.value.error_dict

    def test_product_sku_case_insensitive(self, tenant_uuid):
        """SKU é case-insensitive (único)."""
        criar_produto(
            tenant_id=tenant_uuid,
            short_name="Produto A",
            base_unit=UnidadeBase.UNIDADE,
            display_unit="un",
            display_factor=Decimal("1"),
            sku="ABC123",
        )
        with pytest.raises(ValidationError) as exc:
            criar_produto(
                tenant_id=tenant_uuid,
                short_name="Produto B",
                base_unit=UnidadeBase.UNIDADE,
                display_unit="un",
                display_factor=Decimal("1"),
                sku="abc123",  # Mesmo SKU, caso diferente
            )
        assert "sku" in exc.value.error_dict


@pytest.mark.django_db
class TestLotAndExpiry:
    """Problemas 1-2: Lote obrigatório se track_lots, validade obrigatória se lote."""

    def test_lot_mandatory_if_track_lots(self, tenant_uuid):
        """Lote obrigatório quando product.track_lots=True."""
        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Iogurte",
            base_unit=UnidadeBase.MILILITRO,
            display_unit="l",
            display_factor=Decimal("1000"),
            track_lots=True,
        )

        serializer = RevisaoDeLinhaInSerializer(context=_contexto_do_pedido(tenant_uuid), data={
            "product": str(produto.pk),
            "lot_code": "",  # Sem lote
            "quantity_received": Decimal("100"),
            "kind": "goods",
        })
        assert not serializer.is_valid()
        assert "lot_code" in serializer.errors

    def test_lot_optional_if_not_track_lots(self, tenant_uuid):
        """Lote opcional quando product.track_lots=False."""
        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Sal",
            base_unit=UnidadeBase.GRAMA,
            display_unit="kg",
            display_factor=Decimal("1000"),
            track_lots=False,
        )

        serializer = RevisaoDeLinhaInSerializer(context=_contexto_do_pedido(tenant_uuid), data={
            "product": str(produto.pk),
            "lot_code": "",  # Sem lote, mas é ok
            "quantity_received": Decimal("100"),
            "kind": "goods",
        })
        assert serializer.is_valid()

    def test_expiry_mandatory_if_lot_provided(self, tenant_uuid):
        """Validade obrigatória quando lot_code fornecido."""
        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Chocolate",
            base_unit=UnidadeBase.GRAMA,
            display_unit="kg",
            display_factor=Decimal("1000"),
        )

        serializer = RevisaoDeLinhaInSerializer(context=_contexto_do_pedido(tenant_uuid), data={
            "product": str(produto.pk),
            "lot_code": "LOTE123",
            "expires_at": None,  # Sem validade
            "quantity_received": Decimal("100"),
            "kind": "goods",
        })
        assert not serializer.is_valid()
        assert "expires_at" in serializer.errors

    def test_expiry_not_required_if_no_lot(self, tenant_uuid):
        """Validade opcional quando sem lote."""
        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Sal Fino",
            base_unit=UnidadeBase.GRAMA,
            display_unit="kg",
            display_factor=Decimal("1000"),
        )

        serializer = RevisaoDeLinhaInSerializer(context=_contexto_do_pedido(tenant_uuid), data={
            "product": str(produto.pk),
            "lot_code": "",  # Sem lote
            "expires_at": None,  # Sem validade (ok)
            "quantity_received": Decimal("100"),
            "kind": "goods",
        })
        assert serializer.is_valid()


@pytest.mark.django_db
class TestTrackLotsImmutable:
    """Problema 4: track_lots não pode mudar se há stock."""

    def test_track_lots_can_change_without_stock(self, tenant_uuid):
        """track_lots pode mudar sem stock."""
        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Arroz",
            base_unit=UnidadeBase.GRAMA,
            display_unit="kg",
            display_factor=Decimal("1000"),
            track_lots=False,
        )
        # Mudar track_lots sem stock: OK
        produto_atualizado = actualizar_produto(
            tenant_id=tenant_uuid,
            produto=produto,
            campos={"track_lots": True},
        )
        assert produto_atualizado.track_lots is True

    def test_track_lots_cannot_change_with_stock(self, tenant_uuid, tenant_ctx):
        """track_lots não pode mudar se há stock."""
        # Criar localização
        loc = Location.objects.create(
            tenant_id=tenant_uuid, name="Armazém", position=0
        )

        # Criar produto sem track_lots
        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Feijão",
            base_unit=UnidadeBase.GRAMA,
            display_unit="kg",
            display_factor=Decimal("1000"),
            track_lots=False,
        )

        # Uma entrada no ledger é o que cria o StockLevel
        with tenant_ctx(tenant_uuid):
            _receber(
                tenant_id=tenant_uuid,
                product_id=produto.pk,
                location_id=loc.pk,
                quantidade=Decimal("100"),
            )

        # Tentar mudar track_lots: DEVE FALHAR
        with pytest.raises(ValidationError) as exc:
            actualizar_produto(
                tenant_id=tenant_uuid,
                produto=produto,
                campos={"track_lots": True},
            )
        assert "track_lots" in exc.value.error_dict


@pytest.mark.django_db
class TestStockCount:
    """Problema 5: Contagem de stock."""

    def test_open_count(self, tenant_uuid, tenant_ctx):
        """Abre uma contagem."""
        loc = Location.objects.create(
            tenant_id=tenant_uuid, name="Frio", position=0
        )

        with tenant_ctx(tenant_uuid):
            contagem = abrir_contagem(tenant_id=tenant_uuid, location_id=loc.pk)

        assert contagem.status == "open"
        assert contagem.location_id == loc.pk

    def test_add_line_to_count(self, tenant_uuid, tenant_ctx):
        """Adiciona linha à contagem com SKU."""
        loc = Location.objects.create(
            tenant_id=tenant_uuid, name="Prateleira", position=0
        )
        contagem = StockCount.objects.create(
            tenant_id=tenant_uuid, location=loc, status="open"
        )
        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Leite Integral",
            base_unit=UnidadeBase.MILILITRO,
            display_unit="l",
            display_factor=Decimal("1000"),
            sku="LEITE001",
        )

        with tenant_ctx(tenant_uuid):
            linha = adicionar_linha_contagem(
                tenant_id=tenant_uuid,
                stock_count_id=contagem.pk,
                sku="LEITE001",
                quantity_counted=Decimal("50"),
            )

        assert linha.product_id == produto.pk
        assert linha.quantity_counted == Decimal("50")

    def test_count_summary(self, tenant_uuid, tenant_ctx):
        """Resumo de contagem."""
        loc = Location.objects.create(
            tenant_id=tenant_uuid, name="Congelador", position=0
        )
        contagem = StockCount.objects.create(
            tenant_id=tenant_uuid, location=loc, status="open"
        )

        resumo = resumo_contagem(tenant_id=tenant_uuid, stock_count_id=contagem.pk)
        assert resumo["total_lines"] == 0
        assert resumo["lines_counted"] == 0
        assert resumo["can_close"] is True  # Sem linhas = pode fechar

    def test_close_count_empty(self, tenant_uuid, tenant_ctx):
        """Fecha contagem vazia."""
        loc = Location.objects.create(
            tenant_id=tenant_uuid, name="Armazém B", position=0
        )
        contagem = StockCount.objects.create(
            tenant_id=tenant_uuid, location=loc, status="open"
        )

        with tenant_ctx(tenant_uuid):
            contagem_fechada = fechar_contagem(tenant_id=tenant_uuid, stock_count_id=contagem.pk)

        assert contagem_fechada.status == "closed"
        assert contagem_fechada.closed_at is not None

    def test_close_count_with_variance_writes_an_adjustment(self, tenant_uuid, tenant_ctx):
        """Fechar com diferença grava um `adjustment` no ledger e o nível segue-o.

        O stock é um ledger (CLAUDE.md): a diferença entre o contado e o
        esperado nunca se escreve no `StockLevel`. O que se afirma é que o
        movimento existe, com a diferença e a referência da contagem, e que o
        nível recalculado a partir dos movimentos é o que se contou.
        """
        loc = Location.objects.create(tenant_id=tenant_uuid, name="Despensa", position=0)
        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Azeite",
            base_unit=UnidadeBase.MILILITRO,
            display_unit="l",
            display_factor=Decimal("1000"),
            sku="AZEITE001",
        )
        with tenant_ctx(tenant_uuid):
            _receber(
                tenant_id=tenant_uuid,
                product_id=produto.pk,
                location_id=loc.pk,
                quantidade=Decimal("100"),
            )
            contagem = abrir_contagem(tenant_id=tenant_uuid, location_id=loc.pk)
            linha = adicionar_linha_contagem(
                tenant_id=tenant_uuid,
                stock_count_id=contagem.pk,
                sku="azeite001",
                quantity_counted=Decimal("94"),
            )
            assert linha.quantity_expected == Decimal("100")

            fechada = fechar_contagem(
                tenant_id=tenant_uuid, stock_count_id=contagem.pk, user_name="Dono"
            )

            ajuste = StockMovement.objects.get(
                tenant_id=tenant_uuid, product_id=produto.pk, movement_type="adjustment"
            )
            nivel = StockLevel.objects.get(
                tenant_id=tenant_uuid, product_id=produto.pk, location_id=loc.pk, lot=None
            )

        assert fechada.status == "closed"
        assert ajuste.quantity == Decimal("-6")
        assert ajuste.reference == str(contagem.pk)
        assert ajuste.created_by_name == "Dono"
        assert nivel.quantity == Decimal("94")

    def test_close_count_with_uncounted_line_is_refused(self, tenant_uuid, tenant_ctx):
        """Uma linha por contar impede o fecho — e nada vai ao ledger."""
        loc = Location.objects.create(tenant_id=tenant_uuid, name="Bar", position=0)
        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Vinho",
            base_unit=UnidadeBase.MILILITRO,
            display_unit="l",
            display_factor=Decimal("1000"),
            sku="VINHO001",
        )
        with tenant_ctx(tenant_uuid):
            contagem = abrir_contagem(tenant_id=tenant_uuid, location_id=loc.pk)
            adicionar_linha_contagem(
                tenant_id=tenant_uuid,
                stock_count_id=contagem.pk,
                sku="VINHO001",
                quantity_counted=None,
            )
            with pytest.raises(ValidationError) as exc:
                fechar_contagem(tenant_id=tenant_uuid, stock_count_id=contagem.pk)
            assert not StockMovement.objects.filter(
                tenant_id=tenant_uuid, product_id=produto.pk
            ).exists()

        assert "stock_count" in exc.value.error_dict


@pytest.mark.django_db
class TestSKUInSerialization:
    """Validar que SKU aparece em serializers."""

    def test_product_out_serializer_includes_sku(self, tenant_uuid):
        """ProdutoOutSerializer inclui SKU."""
        from apps.catalog.serializers import ProdutoOutSerializer

        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Café",
            base_unit=UnidadeBase.GRAMA,
            display_unit="kg",
            display_factor=Decimal("1000"),
            sku="CAFE001",
        )

        serializer = ProdutoOutSerializer(produto)
        assert serializer.data["sku"] == "CAFE001"
