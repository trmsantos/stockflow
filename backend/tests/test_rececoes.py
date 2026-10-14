"""Testes da API de receções (fatia 2 da recepção de mercadoria)."""


import pytest
from django.test import Client
from rest_framework.test import APIClient

from apps.accounts.models import Papel, User
from apps.accounts.services import conceder_pertenca, criar_tenant
from apps.catalog.models import Supplier
from apps.inventory.models import Location
from apps.purchasing.models import Receipt
from apps.shared.db import tenant_scope

CREDENCIAL = "trigo-fresco-ao-amanhecer-7"


@pytest.mark.django_db(transaction=True)
class TestRececoes:
    """Happy path: criar receção, rever linha, confirmar."""

    def test_criar_rececao_sem_documento(self):
        """POST /receipts sem document: zero linhas, pode acrescentar."""
        tenant = criar_tenant(name="Test")

        with tenant_scope(tenant.id):
            user = User.objects.create_user("test@test.com", CREDENCIAL)
            conceder_pertenca(user=user, tenant_id=tenant.id, role=Papel.OWNER, display_name="Test")

            loc = Location.objects.create(tenant=tenant, name="Loja", position=1)
            supplier = Supplier.objects.create(tenant=tenant, name="Fornecedor", nif="987654321")

        # Login
        client = Client()
        response = client.post(
            "/api/v1/auth/login",
            {"email": "test@test.com", "password": CREDENCIAL},
            content_type="application/json"
        )
        assert response.status_code == 200

        # Criar receção
        api_client = APIClient()
        cookies = response.cookies
        for key, value in cookies.items():
            api_client.cookies[key] = value.value

        data = {
            "location": str(loc.id),
            "supplier_name": "Fornecedor",
            "supplier_nif": "987654321",
            "doc_type": "FT",
            "supplier": str(supplier.id),
        }

        response = api_client.post("/api/v1/receipts", data, format="json")
        assert response.status_code == 201
        receipt_id = response.data["id"]

        # Verificar que começa vazio
        response = api_client.get(f"/api/v1/receipts/{receipt_id}/lines")
        assert response.status_code == 200
        assert response.data["count"] == 0

    def test_confirmar_rececao_sem_linhas_revistas_falha(self):
        """POST /receipts/{id}/confirmation sem linhas confirmadas: 409."""
        tenant = criar_tenant(name="Test")

        with tenant_scope(tenant.id):
            user = User.objects.create_user("test@test.com", CREDENCIAL)
            conceder_pertenca(user=user, tenant_id=tenant.id, role=Papel.OWNER, display_name="Test")

            loc = Location.objects.create(tenant=tenant, name="Loja", position=1)
            supplier = Supplier.objects.create(tenant=tenant, name="Fornecedor", nif="987654321")

            from django.utils import timezone
            receipt = Receipt.objects.create(
                tenant=tenant,
                location=loc,
                supplier=supplier,
                supplier_name="Fornecedor",
                supplier_nif="987654321",
                doc_type="FT",
                received_at=timezone.now(),
            )

        # Login
        client = Client()
        response = client.post(
            "/api/v1/auth/login",
            {"email": "test@test.com", "password": CREDENCIAL},
            content_type="application/json"
        )
        assert response.status_code == 200

        # Chamar endpoint
        api_client = APIClient()
        cookies = response.cookies
        for key, value in cookies.items():
            api_client.cookies[key] = value.value

        response = api_client.post(f"/api/v1/receipts/{receipt.id}/confirmation")
        assert response.status_code == 409
        assert "sem_linhas_revistas" in response.data.get("code", "")

    def test_recepcao_outro_tenant_404(self):
        """GET /receipts/{id} de outro tenant: 404."""
        tenant1 = criar_tenant(name="Test1")
        tenant2 = criar_tenant(name="Test2")

        with tenant_scope(tenant1.id):
            user1 = User.objects.create_user("test1@test.com", CREDENCIAL)
            conceder_pertenca(user=user1, tenant_id=tenant1.id, role=Papel.OWNER, display_name="Test1")

            loc = Location.objects.create(tenant=tenant1, name="Loja", position=1)
            supplier = Supplier.objects.create(tenant=tenant1, name="Fornecedor", nif="111111111")

            from django.utils import timezone
            receipt = Receipt.objects.create(
                tenant=tenant1,
                location=loc,
                supplier=supplier,
                supplier_name="Fornecedor",
                supplier_nif="111111111",
                doc_type="FT",
                received_at=timezone.now(),
            )

        # Criar utilizador no tenant2
        with tenant_scope(tenant2.id):
            user2 = User.objects.create_user("test2@test.com", CREDENCIAL)
            conceder_pertenca(user=user2, tenant_id=tenant2.id, role=Papel.OWNER, display_name="Test2")

        # Login com user2 (tenant2)
        client = Client()
        response = client.post(
            "/api/v1/auth/login",
            {"email": "test2@test.com", "password": CREDENCIAL},
            content_type="application/json"
        )
        assert response.status_code == 200

        # Tentar acessar receção de tenant1 com credenciais de tenant2
        api_client = APIClient()
        cookies = response.cookies
        for key, value in cookies.items():
            api_client.cookies[key] = value.value

        response = api_client.get(f"/api/v1/receipts/{receipt.id}")
        assert response.status_code == 404
