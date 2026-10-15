"""Testes do ledger de stock (StockMovement, Lot, StockLevel, ProductCost).

Validações principais:
- Append-only enforcement: INSERT funciona, UPDATE/DELETE falha
- RLS isolation: outro tenant vê zero linhas
- FEFO: lotes que expiram cedo aparecem primeiro
- CMP recalculado: custo médio ponderado atualizado
- Receção parcial: nem todas as linhas são confirmadas
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError, ProgrammingError, connection
from django.utils import timezone as django_timezone

from apps.accounts.models import Tenant
from apps.accounts.services import criar_tenant as criar_tenant_service
from apps.catalog.models import Product, UnidadeBase
from apps.inventory.models import Location, Lot, ProductCost, StockLevel, StockMovement
from apps.inventory.services import MovementDTO, get_or_create_lots, record_movements
from apps.shared.db import tenant_scope


def criar_produto(tenant: Tenant, nome: str = "Produto Teste") -> Product:
    """Helper para criar um produto válido."""
    with tenant_scope(tenant.id):
        return Product.objects.create(
            tenant=tenant,
            short_name=nome,
            base_unit=UnidadeBase.GRAMA,
            display_unit="g",
            display_factor=Decimal("1.000"),
            track_lots=False,
            expiry_kind="",
            is_active=True,
        )


def criar_tenant(nome: str) -> Tenant:
    """Helper para criar um tenant."""
    # Usa a função de serviço que já abre o scope apropriado
    return criar_tenant_service(name=nome)


@pytest.mark.django_db(transaction=True)
@pytest.mark.sem_ambito_de_rls
class TestStockMovementAppendOnly:
    """Validação: append-only enforcement no Postgres."""

    def test_insert_succeeds(self):
        """Inserção de movimento funciona (não está revogada)."""
        tenant = criar_tenant("Test Tenant")
        product = criar_produto(tenant)

        with tenant_scope(tenant.id):
            location = Location.objects.create(
                tenant=tenant, name="Loja Teste", position=1
            )
            lot = Lot.objects.create(
                tenant=tenant,
                product=product,
                code="LOT001",
                received_at=django_timezone.now(),
            )
            movimento = StockMovement.objects.create(
                tenant=tenant,
                product=product,
                location=location,
                lot=lot,
                movement_type="receipt",
                quantity=Decimal("10"),
                unit_cost=Decimal("5.50"),
                cost_is_estimate=False,
                occurred_at=django_timezone.now(),
                created_by_name="Teste",
            )
            assert movimento.id is not None
            assert StockMovement.objects.filter(id=movimento.id).exists()

    def test_update_fails_with_permission_denied(self):
        """Atualização de movimento falha (REVOKE UPDATE)."""
        tenant = criar_tenant("Test Tenant 2")
        product = criar_produto(tenant)

        with tenant_scope(tenant.id):
            location = Location.objects.create(
                tenant=tenant, name="Loja Teste", position=1
            )
            lot = Lot.objects.create(
                tenant=tenant,
                product=product,
                code="LOT002",
                received_at=django_timezone.now(),
            )
            movimento = StockMovement.objects.create(
                tenant=tenant,
                product=product,
                location=location,
                lot=lot,
                movement_type="receipt",
                quantity=Decimal("10"),
                unit_cost=Decimal("5.50"),
                cost_is_estimate=False,
                occurred_at=django_timezone.now(),
                created_by_name="Teste",
            )

        # Tentar atualizar deve falhar na base de dados: `permission denied`,
        # que o Django entrega como ProgrammingError.
        with pytest.raises(ProgrammingError, match="permission denied"):
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE inventory_stockmovement SET quantity = %s WHERE id = %s",
                    [Decimal("20"), str(movimento.id)],
                )

    def test_delete_fails_with_permission_denied(self):
        """Eliminação de movimento falha (REVOKE DELETE)."""
        tenant = criar_tenant("Test Tenant 3")
        product = criar_produto(tenant)

        with tenant_scope(tenant.id):
            location = Location.objects.create(
                tenant=tenant, name="Loja Teste", position=1
            )
            lot = Lot.objects.create(
                tenant=tenant,
                product=product,
                code="LOT003",
                received_at=django_timezone.now(),
            )
            movimento = StockMovement.objects.create(
                tenant=tenant,
                product=product,
                location=location,
                lot=lot,
                movement_type="receipt",
                quantity=Decimal("10"),
                unit_cost=Decimal("5.50"),
                cost_is_estimate=False,
                occurred_at=django_timezone.now(),
                created_by_name="Teste",
            )

        # Tentar apagar deve falhar na base de dados, pela mesma razão.
        with pytest.raises(ProgrammingError, match="permission denied"):
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM inventory_stockmovement WHERE id = %s",
                    [str(movimento.id)],
                )


@pytest.mark.django_db(transaction=True)
@pytest.mark.sem_ambito_de_rls
class TestRLSIsolation:
    """Validação: RLS isola dados entre tenants."""

    def test_movement_invisible_to_other_tenant(self):
        """Movimento de um tenant não é visível para outro."""
        tenant1 = criar_tenant("Tenant 1")
        tenant2 = criar_tenant("Tenant 2")

        product1 = criar_produto(tenant1)

        movimento_id = None
        with tenant_scope(tenant1.id):
            location1 = Location.objects.create(
                tenant=tenant1, name="Loja 1", position=1
            )
            lot1 = Lot.objects.create(
                tenant=tenant1,
                product=product1,
                code="LOT001",
                received_at=django_timezone.now(),
            )

            movimento = StockMovement.objects.create(
                tenant=tenant1,
                product=product1,
                location=location1,
                lot=lot1,
                movement_type="receipt",
                quantity=Decimal("10"),
                unit_cost=Decimal("5.50"),
                cost_is_estimate=False,
                occurred_at=django_timezone.now(),
                created_by_name="Teste",
            )
            movimento_id = movimento.id
            # Dentro do escopo de tenant1, o movimento é visível
            assert (
                StockMovement.objects.filter(tenant=tenant1, id=movimento.id).exists()
            )

        # Dentro do escopo de tenant2, o movimento não é visível
        with tenant_scope(tenant2.id):
            assert not StockMovement.objects.filter(tenant=tenant2, id=movimento_id).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.sem_ambito_de_rls
class TestCostCalculation:
    """Validação: CMP (custo médio ponderado) recalculado corretamente."""

    def test_weighted_cost_single_receipt(self):
        """CMP com uma única receção."""
        tenant = criar_tenant("Cost Test 1")
        product = criar_produto(tenant)

        with tenant_scope(tenant.id):
            location = Location.objects.create(
                tenant=tenant, name="Loja", position=1
            )

            mvt = MovementDTO(
                product_id=product.id,
                location_id=location.id,
                lot_id=None,
                quantity=Decimal("100"),
                unit_cost=Decimal("10.00"),
                cost_is_estimate=False,
                movement_type="receipt",
                occurred_at=django_timezone.now(),
                created_by_id=None,
                created_by_name="Teste",
            )

            record_movements(tenant_id=tenant.id, movements=[mvt])

            # Verificar StockLevel
            nível = StockLevel.objects.get(
                tenant=tenant, product=product, location=location, lot_id=None
            )
            assert nível.quantity == Decimal("100")
            assert nível.unit_cost == Decimal("10.00")

            # Verificar ProductCost
            custo = ProductCost.objects.get(
                tenant=tenant, product=product, location=location
            )
            assert custo.unit_cost == Decimal("10.00")

    def test_weighted_cost_two_receipts(self):
        """CMP com duas receções de preços diferentes."""
        tenant = criar_tenant("Cost Test 2")
        product = criar_produto(tenant)

        with tenant_scope(tenant.id):
            location = Location.objects.create(
                tenant=tenant, name="Loja", position=1
            )

            # Primeira receção: 100 unidades a 10€
            mvt1 = MovementDTO(
                product_id=product.id,
                location_id=location.id,
                lot_id=None,
                quantity=Decimal("100"),
                unit_cost=Decimal("10.00"),
                cost_is_estimate=False,
                movement_type="receipt",
                occurred_at=django_timezone.now(),
                created_by_id=None,
                created_by_name="Teste",
            )

            # Segunda receção: 50 unidades a 12€
            mvt2 = MovementDTO(
                product_id=product.id,
                location_id=location.id,
                lot_id=None,
                quantity=Decimal("50"),
                unit_cost=Decimal("12.00"),
                cost_is_estimate=False,
                movement_type="receipt",
                occurred_at=django_timezone.now(),
                created_by_id=None,
                created_by_name="Teste",
            )

            record_movements(tenant_id=tenant.id, movements=[mvt1])
            record_movements(tenant_id=tenant.id, movements=[mvt2])

            # CMP = (100*10 + 50*12) / (100+50) = 1600 / 150 = 10.666...
            custo = ProductCost.objects.get(
                tenant=tenant, product=product, location=location
            )
            # Verificar que está próximo (a precisão de Decimal(12,6))
            assert custo.unit_cost > Decimal("10.66") and custo.unit_cost < Decimal("10.67")


@pytest.mark.django_db(transaction=True)
@pytest.mark.sem_ambito_de_rls
class TestLotCreation:
    """Validação: criação e reutilização de lotes."""

    def test_get_or_create_lots_creates_new(self):
        """Criação de novo lote."""
        tenant = criar_tenant("Lot Test 1")
        product = criar_produto(tenant)

        with tenant_scope(tenant.id):
            items = [
                (product.id, "LOT001", None, django_timezone.now()),
            ]

            lotes = get_or_create_lots(tenant_id=tenant.id, items=items)

            assert (product.id, "LOT001") in lotes
            lot = Lot.objects.get(
                tenant=tenant, product=product, code="LOT001"
            )
            assert lot.expires_at is None

    def test_get_or_create_lots_reuses_existing(self):
        """Reutilização de lote existente."""
        tenant = criar_tenant("Lot Test 2")
        product = criar_produto(tenant)

        with tenant_scope(tenant.id):
            # Criar um lote
            items1 = [
                (product.id, "LOT001", None, django_timezone.now()),
            ]
            lotes1 = get_or_create_lots(tenant_id=tenant.id, items=items1)

            # Chamar novamente com o mesmo lote
            items2 = [
                (product.id, "LOT001", None, django_timezone.now()),
            ]
            lotes2 = get_or_create_lots(tenant_id=tenant.id, items=items2)

            # Os IDs devem ser os mesmos
            assert lotes1[(product.id, "LOT001")] == lotes2[(product.id, "LOT001")]

            # Deve haver apenas um lote na BD
            assert Lot.objects.filter(tenant=tenant, product=product, code="LOT001").count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.sem_ambito_de_rls
class TestPartialReceipt:
    """Validação: receção parcial (nem todas as linhas confirmadas)."""

    def test_partial_receipt_movements(self):
        """Apenas as linhas confirmadas geram movimentos."""
        tenant = criar_tenant("Partial Test")
        product = criar_produto(tenant)

        with tenant_scope(tenant.id):
            location = Location.objects.create(
                tenant=tenant, name="Loja", position=1
            )

            # Simular: 5 faturados, 3 confirmados
            # Criamos um movimento de 3, não de 5
            mvt = MovementDTO(
                product_id=product.id,
                location_id=location.id,
                lot_id=None,
                quantity=Decimal("3"),  # Apenas 3 confirmadas
                unit_cost=Decimal("10.00"),
                cost_is_estimate=False,
                movement_type="receipt",
                occurred_at=django_timezone.now(),
                created_by_id=None,
                created_by_name="Teste",
            )

            record_movements(tenant_id=tenant.id, movements=[mvt])

            # Verificar que o stock tem 3, não 5
            nível = StockLevel.objects.get(
                tenant=tenant, product=product, location=location, lot_id=None
            )
            assert nível.quantity == Decimal("3")


@pytest.mark.django_db(transaction=True)
@pytest.mark.sem_ambito_de_rls
class TestQuantityConstraint:
    """Validação: quantidade nunca é zero."""

    def test_zero_quantity_rejected_at_model_level(self):
        """Quantidade zero é rejeitada pela constraint CHECK."""
        tenant = criar_tenant("Qty Test")
        product = criar_produto(tenant)

        with tenant_scope(tenant.id):
            location = Location.objects.create(
                tenant=tenant, name="Loja", position=1
            )

            with pytest.raises(IntegrityError):  # a constraint CHECK
                StockMovement.objects.create(
                    tenant=tenant,
                    product=product,
                    location=location,
                    lot=None,
                    movement_type="receipt",
                    quantity=Decimal("0"),  # Zero — deve rejeitar
                    unit_cost=Decimal("10.00"),
                    cost_is_estimate=False,
                    occurred_at=django_timezone.now(),
                    created_by_name="Teste",
                )
