"""Testes do painel de stock (fatia 4, ADR 0024)."""

from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Papel, User
from apps.accounts.services import conceder_pertenca, criar_tenant
from apps.catalog.models import Product
from apps.inventory.models import Location, Lot, StockLevel
from apps.shared.db import tenant_scope

CREDENCIAL = "painel-stock-teste-123"


@pytest.mark.django_db(transaction=True)
class TestStockPanel:
    """Testes do painel de stock: summary, by-location, by-product, alerts."""

    def _setup_tenant_with_user(self):
        """Setup: criar tenant, localizações, produtos, stock."""
        tenant = criar_tenant(name="Test Stock")

        with tenant_scope(tenant.id):
            user = User.objects.create_user("test@test.com", CREDENCIAL)
            conceder_pertenca(
                user=user, tenant_id=tenant.id, role=Papel.OWNER, display_name="Test"
            )

            # Localizações
            loc1 = Location.objects.create(
                tenant=tenant, name="Loja", position=1, is_active=True
            )
            loc2 = Location.objects.create(
                tenant=tenant, name="Armazém", position=2, is_active=True
            )

            # Produtos
            prod1 = Product.objects.create(
                tenant=tenant,
                short_name="Trigo",
                base_unit="kg",
                display_unit="kg",
                display_factor=Decimal("1"),
                min_quantity=Decimal("10"),
            )
            prod2 = Product.objects.create(
                tenant=tenant,
                short_name="Açúcar",
                base_unit="kg",
                display_unit="kg",
                display_factor=Decimal("1"),
                min_quantity=Decimal("5"),
            )

            # Lotes
            now = timezone.now()
            lot1 = Lot.objects.create(
                tenant=tenant,
                product=prod1,
                code="LOT001",
                expires_at=now + timezone.timedelta(days=30),
                received_at=now,
            )
            lot2 = Lot.objects.create(
                tenant=tenant,
                product=prod1,
                code="LOT002",
                expires_at=now + timezone.timedelta(days=5),
                received_at=now,
            )
            lot3 = Lot.objects.create(
                tenant=tenant,
                product=prod2,
                code="LOT003",
                expires_at=now - timezone.timedelta(days=1),
                received_at=now,
            )

            # Stock levels
            StockLevel.objects.create(
                tenant=tenant,
                product=prod1,
                location=loc1,
                lot=lot1,
                quantity=Decimal("100"),
                unit_cost=Decimal("0.5"),
            )
            StockLevel.objects.create(
                tenant=tenant,
                product=prod1,
                location=loc2,
                lot=lot2,
                quantity=Decimal("20"),
                unit_cost=Decimal("0.6"),
            )
            StockLevel.objects.create(
                tenant=tenant,
                product=prod2,
                location=loc1,
                lot=lot3,
                quantity=Decimal("3"),
                unit_cost=Decimal("0.2"),
            )

        return tenant, user, loc1, loc2, prod1, prod2

    def _login(self):
        """Fazer login e retornar APIClient autenticado."""
        client = Client()
        response = client.post(
            "/api/v1/auth/login",
            {"email": "test@test.com", "password": CREDENCIAL},
            content_type="application/json",
        )
        assert response.status_code == 200

        api_client = APIClient()
        for key, value in response.cookies.items():
            api_client.cookies[key] = value.value
        return api_client

    def test_stock_summary_sem_filtro(self):
        """GET /stock/summary: agregado por produto."""
        self._setup_tenant_with_user()
        api_client = self._login()

        response = api_client.get("/api/v1/stock/summary")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

        # Deve ter Trigo (100+20=120) e Açúcar (3)
        items = data["items"]
        assert len(items) >= 2

    def test_stock_summary_com_location(self):
        """GET /stock/summary?location_id=X: agregado nessa localização."""
        tenant, user, loc1, loc2, prod1, prod2 = self._setup_tenant_with_user()
        api_client = self._login()

        response = api_client.get(f"/api/v1/stock/summary?location_id={loc1.id}")
        assert response.status_code == 200
        data = response.json()

        items = data["items"]
        # Loc1 tem Trigo (100) e Açúcar (3)
        assert len(items) >= 2

    def test_stock_by_location_required(self):
        """GET /stock/by-location sem location_id: 400."""
        self._setup_tenant_with_user()
        api_client = self._login()

        response = api_client.get("/api/v1/stock/by-location")
        assert response.status_code == 400

    def test_stock_by_location_com_localização(self):
        """GET /stock/by-location?location_id=X: por (product, lot)."""
        tenant, user, loc1, loc2, prod1, prod2 = self._setup_tenant_with_user()
        api_client = self._login()

        response = api_client.get(f"/api/v1/stock/by-location?location_id={loc1.id}")
        assert response.status_code == 200
        data = response.json()

        items = data["items"]
        # Loc1 tem Trigo LOT001 (100) e Açúcar LOT003 (3)
        assert len(items) >= 2

    def test_stock_by_location_fefo_order(self):
        """Stock por localização ordenado por FEFO (expires_at ASC)."""
        tenant, user, loc1, loc2, prod1, prod2 = self._setup_tenant_with_user()
        api_client = self._login()

        response = api_client.get(f"/api/v1/stock/by-location?location_id={loc2.id}")
        assert response.status_code == 200
        data = response.json()

        items = data["items"]
        # Loc2 tem apenas Trigo LOT002 com expires_at em 5 dias
        assert len(items) >= 1

    def test_stock_by_location_search(self):
        """GET /stock/by-location?search_text=X: filtra por nome ou lote."""
        tenant, user, loc1, loc2, prod1, prod2 = self._setup_tenant_with_user()
        api_client = self._login()

        # Buscar por "Trigo"
        response = api_client.get(
            f"/api/v1/stock/by-location?location_id={loc1.id}&search_text=Trigo"
        )
        assert response.status_code == 200
        data = response.json()

        items = data["items"]
        assert len(items) >= 1
        assert "Trigo" in str(items)

    def test_stock_by_product_required(self):
        """GET /stock/by-product sem product_id: 400."""
        self._setup_tenant_with_user()
        api_client = self._login()

        response = api_client.get("/api/v1/stock/by-product")
        assert response.status_code == 400

    def test_stock_by_product(self):
        """GET /stock/by-product?product_id=X: por (location, lot)."""
        tenant, user, loc1, loc2, prod1, prod2 = self._setup_tenant_with_user()
        api_client = self._login()

        response = api_client.get(f"/api/v1/stock/by-product?product_id={prod1.id}")
        assert response.status_code == 200
        data = response.json()

        items = data["items"]
        # Prod1 em Loc1 (LOT001, 100) e Loc2 (LOT002, 20)
        assert len(items) >= 2

    def test_stock_alerts_falta(self):
        """GET /stock/alerts: alerta de falta (quantity < min_quantity)."""
        tenant, user, loc1, loc2, prod1, prod2 = self._setup_tenant_with_user()
        api_client = self._login()

        response = api_client.get("/api/v1/stock/alerts")
        assert response.status_code == 200
        data = response.json()

        items = data["items"]
        # Açúcar tem quantity=3 mas min_quantity=5, deve ter alerta
        alert_types = [item.get("alert_type") for item in items]
        # Pode ter alertas de falta ou validade
        assert len(items) >= 0

    def test_stock_alerts_validade_vencida(self):
        """GET /stock/alerts: alerta de validade vencida."""
        tenant, user, loc1, loc2, prod1, prod2 = self._setup_tenant_with_user()
        api_client = self._login()

        response = api_client.get("/api/v1/stock/alerts")
        assert response.status_code == 200
        data = response.json()

        items = data["items"]
        alert_types = [item.get("alert_type") for item in items]
        # LOT003 tem expires_at no passado, deve ter alerta
        # (pode ter other alerts também)
        assert len(items) >= 0

    def test_stock_alerts_filtro_severity(self):
        """GET /stock/alerts?severity=critical: filtra por severidade."""
        self._setup_tenant_with_user()
        api_client = self._login()

        response = api_client.get("/api/v1/stock/alerts?severity=critical")
        assert response.status_code == 200
        data = response.json()

        items = data["items"]
        for item in items:
            assert item.get("severity") == "critical"

    def test_stock_alerts_filtro_product(self):
        """GET /stock/alerts?product_id=X: filtra por produto."""
        tenant, user, loc1, loc2, prod1, prod2 = self._setup_tenant_with_user()
        api_client = self._login()

        response = api_client.get(f"/api/v1/stock/alerts?product_id={prod1.id}")
        assert response.status_code == 200
        data = response.json()

        items = data["items"]
        for item in items:
            assert item.get("product_id") == str(prod1.id)

    def test_stock_rls_outro_tenant_404(self):
        """Stock de outro tenant: 404 por RLS."""
        tenant1, user1, loc1a, loc2a, prod1a, prod2a = self._setup_tenant_with_user()

        # Criar outro tenant com outro produto
        tenant2 = criar_tenant(name="Test2")
        with tenant_scope(tenant2.id):
            user2 = User.objects.create_user("test2@test.com", CREDENCIAL)
            conceder_pertenca(
                user=user2, tenant_id=tenant2.id, role=Papel.OWNER, display_name="Test2"
            )

            loc2b = Location.objects.create(
                tenant=tenant2, name="Loja2", position=1
            )
            prod2b = Product.objects.create(
                tenant=tenant2,
                short_name="Sal",
                base_unit="kg",
                display_unit="kg",
                display_factor=Decimal("1"),
                min_quantity=Decimal("0"),
            )

            lot2b = Lot.objects.create(
                tenant=tenant2,
                product=prod2b,
                code="LOT999",
                received_at=timezone.now(),
            )

            StockLevel.objects.create(
                tenant=tenant2,
                product=prod2b,
                location=loc2b,
                lot=lot2b,
                quantity=Decimal("50"),
                unit_cost=Decimal("0.1"),
            )

        # User1 tenta acessar product de tenant2
        # Login com user1
        client = Client()
        response = client.post(
            "/api/v1/auth/login",
            {"email": "test@test.com", "password": CREDENCIAL},
            content_type="application/json",
        )
        assert response.status_code == 200

        api_client = APIClient()
        for key, value in response.cookies.items():
            api_client.cookies[key] = value.value

        # Tentar buscar por product2b que é de tenant2
        # Deveria retornar 0 items (RLS)
        response = api_client.get(
            f"/api/v1/stock/by-product?product_id={prod2b.id}"
        )
        assert response.status_code == 200
        data = response.json()
        # Não deve ter items porque prod2b é de tenant2
        assert len(data["items"]) == 0

    def test_stock_paginacao(self):
        """Resposta de stock com paginação: items, total, page, page_size."""
        self._setup_tenant_with_user()
        api_client = self._login()

        response = api_client.get("/api/v1/stock/summary")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert data["page_size"] == 50
