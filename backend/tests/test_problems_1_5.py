"""Testes para problemas 1-5 (SKU, lote/validade, track_lots, contagem)."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.catalog.models import UnidadeBase
from apps.catalog.services import actualizar_produto, criar_produto
from apps.inventory.count_services import (
    abrir_contagem,
    adicionar_linha_contagem,
    fechar_contagem,
    resumo_contagem,
)
from apps.inventory.models import Location, StockCount
from apps.purchasing.serializers import RevisaoDeLinhaInSerializer


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

        serializer = RevisaoDeLinhaInSerializer(data={
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

        serializer = RevisaoDeLinhaInSerializer(data={
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

        serializer = RevisaoDeLinhaInSerializer(data={
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

        serializer = RevisaoDeLinhaInSerializer(data={
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

        # Criar um lote sintético e movimento para ter stock
        from apps.inventory.models import Lot
        from apps.inventory.services import record_movement

        lote = Lot.objects.create(
            tenant_id=tenant_uuid,
            product=produto,
            code="__synthetic__",
            received_at=timezone.now(),
        )

        # Registrar movimento para criar StockLevel
        with tenant_ctx(tenant_uuid):
            record_movement(
                tenant_id=tenant_uuid,
                product_id=produto.pk,
                location_id=loc.pk,
                lot_id=lote.pk,
                movement_type="receipt",
                quantity=Decimal("100"),
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
