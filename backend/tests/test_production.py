"""Testes da produção de receitas (fatia 6, ADR 0026)."""

from __future__ import annotations

import pytest
from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.accounts.services import criar_tenant, conceder_pertenca
from apps.accounts.models import Papel, User
from apps.catalog.models import Product, UnidadeBase
from apps.inventory.models import Location, Lot, StockLevel, StockMovement
from apps.recipes.models import Recipe, RecipeLineItem
from apps.recipes.services import produzir
from apps.shared.db import tenant_scope


CREDENCIAL = "produzir-teste-123"


@pytest.mark.django_db(transaction=True)
class TestProducao:
    """Testes da produção de receitas com FEFO, yield_factor e lotes sintéticos."""

    def _setup_tenant_com_usuario(self):
        """Setup: criar tenant, localizações, produtos, receita."""
        tenant = criar_tenant(name="Test Produção")

        with tenant_scope(tenant.id):
            user = User.objects.create_user("prod@test.com", CREDENCIAL)
            conceder_pertenca(
                user=user, tenant_id=tenant.id, role=Papel.OWNER, display_name="Test"
            )

            # Localizações
            loc = Location.objects.create(
                tenant=tenant, name="Cozinha", position=1, is_active=True
            )

            # Produtos
            massa = Product.objects.create(
                tenant=tenant,
                short_name="Massa",
                base_unit=UnidadeBase.GRAMA,
                display_unit=UnidadeBase.GRAMA,
                display_factor=Decimal("1"),
                min_quantity=Decimal("0"),
                track_lots=False,  # Ingrediente genérico
            )

            ovos = Product.objects.create(
                tenant=tenant,
                short_name="Ovos",
                base_unit=UnidadeBase.UNIDADE,
                display_unit=UnidadeBase.UNIDADE,
                display_factor=Decimal("1"),
                min_quantity=Decimal("0"),
                track_lots=False,
            )

            pasteis = Product.objects.create(
                tenant=tenant,
                short_name="Pastéis de Nata",
                base_unit=UnidadeBase.UNIDADE,
                display_unit=UnidadeBase.UNIDADE,
                display_factor=Decimal("1"),
                min_quantity=Decimal("0"),
                track_lots=True,  # Produto acabado com rastreio
            )

            # Receita: 100 pastéis com yield_factor 0.9
            receita = Recipe.objects.create(
                tenant=tenant,
                product=pasteis,
                is_active=True,
                yield_factor=Decimal("0.9"),
            )

            # Linhas: 10 g de massa + 5 ovos por receita
            # (quantidade_per_base_unit está em unidade base do ingrediente)
            RecipeLineItem.objects.create(
                tenant=tenant,
                recipe=receita,
                ingredient_product=massa,
                quantity_per_base_unit=Decimal("10"),  # 10 g (UnidadeBase.GRAMA)
            )

            RecipeLineItem.objects.create(
                tenant=tenant,
                recipe=receita,
                ingredient_product=ovos,
                quantity_per_base_unit=Decimal("5"),  # 5 ovos (UnidadeBase.UNIDADE)
            )

            return tenant, user, loc, massa, ovos, pasteis, receita

    def test_producao_simples_com_stock_exato(self):
        """Caso 3: Stock exato — produz 100 pastéis com os 100/0.9 kg de massa e 100/0.9*5 ovos."""
        tenant, user, loc, massa, ovos, pasteis, receita = (
            self._setup_tenant_com_usuario()
        )

        with tenant_scope(tenant.id):
            now = timezone.now()

            # Setup stock: massa
            # Para 100 pastéis: quantidade_base = 100 / 0.9 = 111.111...,
            # qty_massa = 10 * 111.111... = 1111.111... g
            lote_massa = Lot.objects.create(
                tenant=tenant,
                product=massa,
                code="__massa_id__",
                expires_at=None,
                received_at=now,
            )
            StockLevel.objects.create(
                tenant=tenant,
                product=massa,
                location=loc,
                lot=lote_massa,
                quantity=Decimal("1112"),  # Suficiente para 100 pastéis
                unit_cost=Decimal("0.5"),
            )

            # Setup stock: ovos
            lote_ovos = Lot.objects.create(
                tenant=tenant,
                product=ovos,
                code="__ovos_id__",
                expires_at=None,
                received_at=now,
            )
            StockLevel.objects.create(
                tenant=tenant,
                product=ovos,
                location=loc,
                lot=lote_ovos,
                quantity=Decimal("556"),  # Suficiente (100/0.9 * 5 = 555.555...)
                unit_cost=Decimal("0.1"),
            )

            # Produz 100 pastéis
            production_id = produzir(
                tenant_id=tenant.id,
                recipe_id=receita.id,
                quantity=Decimal("100"),
                location_id=loc.id,
                user=user,
            )

            # Verifica production_id
            assert production_id is not None

            # Verifica 2 movimentos (out + in)
            movimentos = StockMovement.objects.filter(
                tenant=tenant, production_id=production_id
            ).order_by("movement_type")
            assert movimentos.count() == 2

            # Verifica production_out
            out1 = movimentos.filter(product=massa).first()
            assert out1 is not None
            assert out1.movement_type == "production_out"
            assert out1.quantity == -Decimal("111.111")

            out2 = movimentos.filter(product=ovos).first()
            assert out2 is not None
            assert out2.movement_type == "production_out"
            assert out2.quantity == Decimal("-555.555")

            # Verifica production_in
            in_mov = movimentos.filter(product=pasteis).first()
            assert in_mov is not None
            assert in_mov.movement_type == "production_in"
            assert in_mov.quantity == Decimal("100")

            # Verifica que o stock foi debitado
            nivel_massa = StockLevel.objects.get(
                tenant=tenant, product=massa, location=loc
            )
            assert nivel_massa.quantity == Decimal("0")

            nivel_ovos = StockLevel.objects.get(
                tenant=tenant, product=ovos, location=loc
            )
            assert nivel_ovos.quantity == Decimal("0")

            # Verifica que o stock de pastéis foi creditado (com lote sintético)
            nivel_pasteis = StockLevel.objects.get(
                tenant=tenant, product=pasteis, location=loc
            )
            assert nivel_pasteis.quantity == Decimal("100")

            # Verifica lote sintético
            lote_pasteis = nivel_pasteis.lot
            assert lote_pasteis is not None
            assert lote_pasteis.code == f"__{production_id}__"

    def test_producao_com_multiplos_lotes_fefo(self):
        """Caso 2: Múltiplos lotes FEFO — sorteia somas suficientes, sai por ordem."""
        tenant, user, loc, massa, ovos, pasteis, receita = (
            self._setup_tenant_com_usuario()
        )

        with tenant_scope(tenant.id):
            now = timezone.now()

            # Setup stock: dois lotes de massa (FEFO)
            # Lote 1: expira em 5 dias, tem 50kg
            lote_massa_1 = Lot.objects.create(
                tenant=tenant,
                product=massa,
                code="MASSA_001",
                expires_at=now + timezone.timedelta(days=5),
                received_at=now - timezone.timedelta(days=1),
            )
            StockLevel.objects.create(
                tenant=tenant,
                product=massa,
                location=loc,
                lot=lote_massa_1,
                quantity=Decimal("50"),
                unit_cost=Decimal("0.5"),
            )

            # Lote 2: expira em 10 dias, tem 70kg (soma > 111.111 necessários)
            lote_massa_2 = Lot.objects.create(
                tenant=tenant,
                product=massa,
                code="MASSA_002",
                expires_at=now + timezone.timedelta(days=10),
                received_at=now,
            )
            StockLevel.objects.create(
                tenant=tenant,
                product=massa,
                location=loc,
                lot=lote_massa_2,
                quantity=Decimal("70"),
                unit_cost=Decimal("0.4"),
            )

            # Setup stock: ovos (suficiente)
            lote_ovos = Lot.objects.create(
                tenant=tenant,
                product=ovos,
                code="__ovos_id__",
                expires_at=None,
                received_at=now,
            )
            StockLevel.objects.create(
                tenant=tenant,
                product=ovos,
                location=loc,
                lot=lote_ovos,
                quantity=Decimal("560"),
                unit_cost=Decimal("0.1"),
            )

            # Produz 100 pastéis — consome 111.111 kg de massa
            # FEFO escolhe lote 1 (expires_at menor) até esgotar
            production_id = produzir(
                tenant_id=tenant.id,
                recipe_id=receita.id,
                quantity=Decimal("100"),
                location_id=loc.id,
                user=user,
            )

            assert production_id is not None

            # Verifica saldos
            nivel_1 = StockLevel.objects.get(
                tenant=tenant, product=massa, location=loc, lot=lote_massa_1
            )
            assert nivel_1.quantity == Decimal("0")  # Lote 1 foi consumido

            nivel_2 = StockLevel.objects.get(
                tenant=tenant, product=massa, location=loc, lot=lote_massa_2
            )
            # 70 - 61.111 = 8.889
            assert nivel_2.quantity == Decimal("8.889")

    def test_ingrediente_novo_sem_stock_retorna_409(self):
        """Caso 1: Ingrediente novo (sem stock) → 409."""
        tenant, user, loc, massa, ovos, pasteis, receita = (
            self._setup_tenant_com_usuario()
        )

        with tenant_scope(tenant.id):
            # NÃO cria stock de massa — vai falhar

            # Setup stock: ovos (suficiente)
            now = timezone.now()
            lote_ovos = Lot.objects.create(
                tenant=tenant,
                product=ovos,
                code="__ovos_id__",
                expires_at=None,
                received_at=now,
            )
            StockLevel.objects.create(
                tenant=tenant,
                product=ovos,
                location=loc,
                lot=lote_ovos,
                quantity=Decimal("560"),
                unit_cost=Decimal("0.1"),
            )

            # Tenta produzir — massa não tem stock
            with pytest.raises(ValidationError) as exc_info:
                produzir(
                    tenant_id=tenant.id,
                    recipe_id=receita.id,
                    quantity=Decimal("100"),
                    location_id=loc.id,
                    user=user,
                )

            # Verifica que falhou por falta de stock
            assert exc_info.value.code == "insufficient_stock"

    def test_produto_acabado_track_lots_true_gera_lote_sintetico(self):
        """Caso 4: Produto acabado com track_lots=True → lote sintético __<production_id>__."""
        tenant, user, loc, massa, ovos, pasteis, receita = (
            self._setup_tenant_com_usuario()
        )

        with tenant_scope(tenant.id):
            now = timezone.now()

            # Setup stock minimal
            lote_massa = Lot.objects.create(
                tenant=tenant,
                product=massa,
                code="__massa_id__",
                expires_at=None,
                received_at=now,
            )
            StockLevel.objects.create(
                tenant=tenant,
                product=massa,
                location=loc,
                lot=lote_massa,
                quantity=Decimal("200"),
                unit_cost=Decimal("0.5"),
            )

            lote_ovos = Lot.objects.create(
                tenant=tenant,
                product=ovos,
                code="__ovos_id__",
                expires_at=None,
                received_at=now,
            )
            StockLevel.objects.create(
                tenant=tenant,
                product=ovos,
                location=loc,
                lot=lote_ovos,
                quantity=Decimal("1000"),
                unit_cost=Decimal("0.1"),
            )

            production_id = produzir(
                tenant_id=tenant.id,
                recipe_id=receita.id,
                quantity=Decimal("100"),
                location_id=loc.id,
                user=user,
            )

            # Verifica lote sintético
            lote = Lot.objects.get(tenant=tenant, product=pasteis)
            assert lote.code == f"__{production_id}__"
            assert lote.expires_at is None  # Sem validade

    def test_produto_acabado_track_lots_false_nao_gera_lote(self):
        """Caso 5: Produto acabado com track_lots=False → lot=NULL."""
        tenant, user, loc, massa, ovos, pasteis, receita = (
            self._setup_tenant_com_usuario()
        )

        with tenant_scope(tenant.id):
            # Muda product_acabado para track_lots=False
            pasteis.track_lots = False
            pasteis.save()

            now = timezone.now()

            # Setup stock
            lote_massa = Lot.objects.create(
                tenant=tenant,
                product=massa,
                code="__massa_id__",
                expires_at=None,
                received_at=now,
            )
            StockLevel.objects.create(
                tenant=tenant,
                product=massa,
                location=loc,
                lot=lote_massa,
                quantity=Decimal("200"),
                unit_cost=Decimal("0.5"),
            )

            lote_ovos = Lot.objects.create(
                tenant=tenant,
                product=ovos,
                code="__ovos_id__",
                expires_at=None,
                received_at=now,
            )
            StockLevel.objects.create(
                tenant=tenant,
                product=ovos,
                location=loc,
                lot=lote_ovos,
                quantity=Decimal("1000"),
                unit_cost=Decimal("0.1"),
            )

            produzir(
                tenant_id=tenant.id,
                recipe_id=receita.id,
                quantity=Decimal("100"),
                location_id=loc.id,
                user=user,
            )

            # Verifica que não há lote
            nivel_pasteis = StockLevel.objects.get(
                tenant=tenant, product=pasteis, location=loc
            )
            assert nivel_pasteis.lot is None

    def test_receita_inativa_retorna_404(self):
        """Receita inativa → 404."""
        tenant, user, loc, massa, ovos, pasteis, receita = (
            self._setup_tenant_com_usuario()
        )

        with tenant_scope(tenant.id):
            receita.is_active = False
            receita.save()

            with pytest.raises(ValidationError) as exc_info:
                produzir(
                    tenant_id=tenant.id,
                    recipe_id=receita.id,
                    quantity=Decimal("100"),
                    location_id=loc.id,
                    user=user,
                )

            assert exc_info.value.code == "recipe_not_found"

    def test_quantidade_zero_retorna_400(self):
        """qty ≤ 0 → 400."""
        tenant, user, loc, massa, ovos, pasteis, receita = (
            self._setup_tenant_com_usuario()
        )

        with tenant_scope(tenant.id):
            with pytest.raises(ValidationError) as exc_info:
                produzir(
                    tenant_id=tenant.id,
                    recipe_id=receita.id,
                    quantity=Decimal("0"),
                    location_id=loc.id,
                    user=user,
                )

            assert exc_info.value.code == "invalid_quantity"

    def test_localizacao_inativa_retorna_409(self):
        """location inativa → 409."""
        tenant, user, loc, massa, ovos, pasteis, receita = (
            self._setup_tenant_com_usuario()
        )

        with tenant_scope(tenant.id):
            loc.is_active = False
            loc.save()

            with pytest.raises(ValidationError) as exc_info:
                produzir(
                    tenant_id=tenant.id,
                    recipe_id=receita.id,
                    quantity=Decimal("100"),
                    location_id=loc.id,
                    user=user,
                )

            assert exc_info.value.code == "location_not_found"

    def test_yield_factor_zero_retorna_409(self):
        """yield_factor ≤ 0 → 409."""
        tenant, user, loc, massa, ovos, pasteis, receita = (
            self._setup_tenant_com_usuario()
        )

        with tenant_scope(tenant.id):
            receita.yield_factor = Decimal("0")
            receita.save()

            with pytest.raises(ValidationError) as exc_info:
                produzir(
                    tenant_id=tenant.id,
                    recipe_id=receita.id,
                    quantity=Decimal("100"),
                    location_id=loc.id,
                    user=user,
                )

            assert exc_info.value.code == "invalid_yield_factor"

    def test_receita_sem_ingredientes_retorna_409(self):
        """receita sem ingredientes → 409."""
        tenant, user, loc, massa, ovos, pasteis, receita = (
            self._setup_tenant_com_usuario()
        )

        with tenant_scope(tenant.id):
            # Apaga todas as linhas
            RecipeLineItem.objects.filter(recipe=receita).delete()

            with pytest.raises(ValidationError) as exc_info:
                produzir(
                    tenant_id=tenant.id,
                    recipe_id=receita.id,
                    quantity=Decimal("100"),
                    location_id=loc.id,
                    user=user,
                )

            assert exc_info.value.code == "recipe_no_ingredients"

    def test_rls_isolation_outro_tenant_nao_ve_receita(self):
        """RLS isolation: outro tenant não vê a receita."""
        tenant1, user1, loc1, massa1, ovos1, pasteis1, receita1 = (
            self._setup_tenant_com_usuario()
        )

        # Cria segundo tenant
        tenant2 = criar_tenant(name="Test Produção 2")

        with tenant_scope(tenant2.id):
            user2 = User.objects.create_user("prod2@test.com", "credencial2")
            conceder_pertenca(
                user=user2, tenant_id=tenant2.id, role=Papel.OWNER, display_name="Test2"
            )

            # Tenta produzir receita de tenant1 no contexto de tenant2
            # Deve parecer que não existe (404)
            with pytest.raises(ValidationError) as exc_info:
                produzir(
                    tenant_id=tenant2.id,
                    recipe_id=receita1.id,
                    quantity=Decimal("100"),
                    location_id=loc1.id,
                    user=user2,
                )

            assert exc_info.value.code == "recipe_not_found"
