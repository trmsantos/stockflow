"""Testes para movimentos de stock manuais (ADR 0025, fatia 5).

Casos de teste:
- Happy path: waste, adjustment, transfer criados com sucesso
- FEFO: saída pega o lote mais antigo
- Validações: reason obrigatório, quantity ≠ 0, lote obrigatório se track_lots=True
- Transfer: atomicamente criados transfer_out + transfer_in
- RLS: outro tenant não vê movimentos
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import Papel, User
from apps.accounts.services import conceder_pertenca, criar_tenant
from apps.catalog.models import Product, UnidadeBase
from apps.inventory.models import Location, Lot, StockLevel, StockMovement
from apps.inventory.services import (
    MovementDTO,
    record_movements,
    registar_adjustment,
    registar_transfer,
    registar_waste,
)
from apps.shared.db import tenant_scope

pytestmark = [pytest.mark.django_db]


def _receber(
    *, tenant_id: UUID, product: Product, location: Location, lote: Lot, user: User,
    quantidade: Decimal,
) -> None:
    """Stock inicial **pelo ledger**, nunca por `StockLevel.objects.create`.

    O nível é a projeção da soma dos movimentos: `record_movements` recalcula-o
    a partir deles, logo um nível escrito à mão desaparece no primeiro
    movimento que lhe toca — e era isso que fazia os testes de ajuste esperarem
    110 e medirem 10.
    """
    record_movements(
        tenant_id=tenant_id,
        movements=[
            MovementDTO(
                product_id=product.id,
                location_id=location.id,
                lot_id=lote.id,
                quantity=quantidade,
                unit_cost=Decimal("1.50"),
                cost_is_estimate=False,
                movement_type="receipt",
                occurred_at=timezone.now(),
                created_by_id=user.id,
                created_by_name=user.email,
            ),
        ],
    )


class TestWasteMovement:
    """Testes para POST /stock/movements/waste."""

    def test_waste_happy_path(self):
        """Teste: desperdício criado com sucesso."""
        # Setup
        tenant = criar_tenant(name="Casa de Testes")
        user = User.objects.create_user(email="op@test.com")

        with tenant_scope(tenant.id):
            conceder_pertenca(
                user=user, tenant_id=tenant.id, role=Papel.STAFF, display_name="Operário"
            )

            product = Product.objects.create(
                tenant=tenant,
                short_name="Pastel",
                base_unit=UnidadeBase.UNIDADE,
                display_unit="un",
                display_factor=1,
                track_lots=False,
            )

            location = Location.objects.create(
                tenant=tenant, name="Balcão", position=0, is_active=True
            )

            lote, _criado = Lot.objects.get_or_create(
                tenant=tenant,
                product=product,
                code=f"__{product.id}__",
                defaults={"received_at": timezone.now()},
            )

            _receber(
                tenant_id=tenant.id, product=product, location=location, lote=lote,
                user=user, quantidade=Decimal("100"),
            )

            # Execute
            movement_id = registar_waste(
                tenant_id=tenant.id,
                product_id=product.id,
                location_id=location.id,
                quantity=Decimal("5"),
                lot_id=lote.id,
                reason="spoiled",
                reason_detail=None,
                user=user,
            )

            # Assert
            assert movement_id is not None
            movimento = StockMovement.objects.get(pk=movement_id)
            assert movimento.movement_type == "waste"
            assert movimento.quantity == Decimal("-5")
            assert movimento.reason == "spoiled"

            # Verificar que StockLevel foi atualizado
            nivel = StockLevel.objects.get(
                tenant=tenant,
                product=product,
                location=location,
                lot=lote,
            )
            assert nivel.quantity == Decimal("95")

    def test_waste_quantity_zero_rejected(self):
        """Teste: quantity=0 deve ser rejeitado."""
        tenant = criar_tenant(name="Casa de Testes")
        user = User.objects.create_user(email="op@test.com")

        with tenant_scope(tenant.id):
            conceder_pertenca(
                user=user, tenant_id=tenant.id, role=Papel.STAFF, display_name="Operário"
            )

            product = Product.objects.create(
                tenant=tenant,
                short_name="Pastel",
                base_unit=UnidadeBase.UNIDADE,
                display_unit="un",
                display_factor=1,
                track_lots=False,
            )

            location = Location.objects.create(
                tenant=tenant, name="Balcão", position=0, is_active=True
            )

            lote, _criado = Lot.objects.get_or_create(
                tenant=tenant,
                product=product,
                code=f"__{product.id}__",
                defaults={"received_at": timezone.now()},
            )

            with pytest.raises(ValidationError):
                registar_waste(
                    tenant_id=tenant.id,
                    product_id=product.id,
                    location_id=location.id,
                    quantity=Decimal("0"),
                    lot_id=lote.id,
                    reason="spoiled",
                    reason_detail=None,
                    user=user,
                )

    def test_waste_invalid_reason_rejected(self):
        """Teste: reason inválido deve ser rejeitado."""
        tenant = criar_tenant(name="Casa de Testes")
        user = User.objects.create_user(email="op@test.com")

        with tenant_scope(tenant.id):
            conceder_pertenca(
                user=user, tenant_id=tenant.id, role=Papel.STAFF, display_name="Operário"
            )

            product = Product.objects.create(
                tenant=tenant,
                short_name="Pastel",
                base_unit=UnidadeBase.UNIDADE,
                display_unit="un",
                display_factor=1,
                track_lots=False,
            )

            location = Location.objects.create(
                tenant=tenant, name="Balcão", position=0, is_active=True
            )

            lote, _criado = Lot.objects.get_or_create(
                tenant=tenant,
                product=product,
                code=f"__{product.id}__",
                defaults={"received_at": timezone.now()},
            )

            with pytest.raises(ValidationError):
                registar_waste(
                    tenant_id=tenant.id,
                    product_id=product.id,
                    location_id=location.id,
                    quantity=Decimal("5"),
                    lot_id=lote.id,
                    reason="invalid_reason",
                    reason_detail=None,
                    user=user,
                )


class TestAdjustmentMovement:
    """Testes para POST /stock/movements/adjustment."""

    def test_adjustment_positive_happy_path(self):
        """Teste: ajuste positivo (entrada) criado com sucesso."""
        tenant = criar_tenant(name="Casa de Testes")
        user = User.objects.create_user(email="op@test.com")

        with tenant_scope(tenant.id):
            conceder_pertenca(
                user=user, tenant_id=tenant.id, role=Papel.STAFF, display_name="Operário"
            )

            product = Product.objects.create(
                tenant=tenant,
                short_name="Pastel",
                base_unit=UnidadeBase.UNIDADE,
                display_unit="un",
                display_factor=1,
                track_lots=False,
            )

            location = Location.objects.create(
                tenant=tenant, name="Balcão", position=0, is_active=True
            )

            lote, _criado = Lot.objects.get_or_create(
                tenant=tenant,
                product=product,
                code=f"__{product.id}__",
                defaults={"received_at": timezone.now()},
            )

            _receber(
                tenant_id=tenant.id, product=product, location=location, lote=lote,
                user=user, quantidade=Decimal("100"),
            )

            movement_id = registar_adjustment(
                tenant_id=tenant.id,
                product_id=product.id,
                location_id=location.id,
                quantity=Decimal("10"),
                lot_id=lote.id,
                reason="other",
                reason_detail="Recontagem descobriu diferença",
                user=user,
            )

            assert movement_id is not None
            movimento = StockMovement.objects.get(pk=movement_id)
            assert movimento.movement_type == "adjustment"
            assert movimento.quantity == Decimal("10")
            assert movimento.reason == "other"

            nivel = StockLevel.objects.get(
                tenant=tenant,
                product=product,
                location=location,
                lot=lote,
            )
            assert nivel.quantity == Decimal("110")

    def test_adjustment_negative_happy_path(self):
        """Teste: ajuste negativo (saída) criado com sucesso."""
        tenant = criar_tenant(name="Casa de Testes")
        user = User.objects.create_user(email="op@test.com")

        with tenant_scope(tenant.id):
            conceder_pertenca(
                user=user, tenant_id=tenant.id, role=Papel.STAFF, display_name="Operário"
            )

            product = Product.objects.create(
                tenant=tenant,
                short_name="Pastel",
                base_unit=UnidadeBase.UNIDADE,
                display_unit="un",
                display_factor=1,
                track_lots=False,
            )

            location = Location.objects.create(
                tenant=tenant, name="Balcão", position=0, is_active=True
            )

            lote, _criado = Lot.objects.get_or_create(
                tenant=tenant,
                product=product,
                code=f"__{product.id}__",
                defaults={"received_at": timezone.now()},
            )

            _receber(
                tenant_id=tenant.id, product=product, location=location, lote=lote,
                user=user, quantidade=Decimal("100"),
            )

            movement_id = registar_adjustment(
                tenant_id=tenant.id,
                product_id=product.id,
                location_id=location.id,
                quantity=Decimal("-15"),
                lot_id=lote.id,
                reason="breakage",
                reason_detail=None,
                user=user,
            )

            assert movement_id is not None
            movimento = StockMovement.objects.get(pk=movement_id)
            assert movimento.movement_type == "adjustment"
            assert movimento.quantity == Decimal("-15")

            nivel = StockLevel.objects.get(
                tenant=tenant,
                product=product,
                location=location,
                lot=lote,
            )
            assert nivel.quantity == Decimal("85")


class TestTransferMovement:
    """Testes para POST /stock/movements/transfer."""

    def test_transfer_happy_path(self):
        """Teste: transferência criada atomicamente com transfer_out + transfer_in."""
        tenant = criar_tenant(name="Casa de Testes")
        user = User.objects.create_user(email="op@test.com")

        with tenant_scope(tenant.id):
            conceder_pertenca(
                user=user, tenant_id=tenant.id, role=Papel.STAFF, display_name="Operário"
            )

            product = Product.objects.create(
                tenant=tenant,
                short_name="Pastel",
                base_unit=UnidadeBase.UNIDADE,
                display_unit="un",
                display_factor=1,
                track_lots=False,
            )

            loc_origem = Location.objects.create(
                tenant=tenant, name="Balcão", position=0, is_active=True
            )
            loc_destino = Location.objects.create(
                tenant=tenant, name="Armazém", position=1, is_active=True
            )

            lote, _criado = Lot.objects.get_or_create(
                tenant=tenant,
                product=product,
                code=f"__{product.id}__",
                defaults={"received_at": timezone.now()},
            )

            _receber(
                tenant_id=tenant.id, product=product, location=loc_origem, lote=lote,
                user=user, quantidade=Decimal("100"),
            )

            out_id, in_id = registar_transfer(
                tenant_id=tenant.id,
                product_id=product.id,
                from_location_id=loc_origem.id,
                to_location_id=loc_destino.id,
                quantity=Decimal("30"),
                lot_id=lote.id,
                user=user,
            )

            assert out_id is not None
            assert in_id is not None

            # Verificar transfer_out
            out_movimento = StockMovement.objects.get(pk=out_id)
            assert out_movimento.movement_type == "transfer_out"
            assert out_movimento.quantity == Decimal("-30")
            assert out_movimento.location_id == loc_origem.id

            # Verificar transfer_in
            in_movimento = StockMovement.objects.get(pk=in_id)
            assert in_movimento.movement_type == "transfer_in"
            assert in_movimento.quantity == Decimal("30")
            assert in_movimento.location_id == loc_destino.id

            # Ambos devem ter o mesmo transfer_id
            assert out_movimento.transfer_id == in_movimento.transfer_id

            # Verificar níveis de stock
            nivel_origem = StockLevel.objects.get(
                tenant=tenant,
                product=product,
                location=loc_origem,
                lot=lote,
            )
            assert nivel_origem.quantity == Decimal("70")

            nivel_destino = StockLevel.objects.get(
                tenant=tenant,
                product=product,
                location=loc_destino,
                lot=lote,
            )
            assert nivel_destino.quantity == Decimal("30")

    def test_transfer_same_location_rejected(self):
        """Teste: transferência para mesma localização deve ser rejeitada."""
        tenant = criar_tenant(name="Casa de Testes")
        user = User.objects.create_user(email="op@test.com")

        with tenant_scope(tenant.id):
            conceder_pertenca(
                user=user, tenant_id=tenant.id, role=Papel.STAFF, display_name="Operário"
            )

            product = Product.objects.create(
                tenant=tenant,
                short_name="Pastel",
                base_unit=UnidadeBase.UNIDADE,
                display_unit="un",
                display_factor=1,
                track_lots=False,
            )

            loc_origem = Location.objects.create(
                tenant=tenant, name="Balcão", position=0, is_active=True
            )

            lote, _criado = Lot.objects.get_or_create(
                tenant=tenant,
                product=product,
                code=f"__{product.id}__",
                defaults={"received_at": timezone.now()},
            )

            _receber(
                tenant_id=tenant.id, product=product, location=loc_origem, lote=lote,
                user=user, quantidade=Decimal("100"),
            )

            with pytest.raises(ValidationError):
                registar_transfer(
                    tenant_id=tenant.id,
                    product_id=product.id,
                    from_location_id=loc_origem.id,
                    to_location_id=loc_origem.id,
                    quantity=Decimal("30"),
                    lot_id=lote.id,
                    user=user,
                )
