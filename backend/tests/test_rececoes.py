"""Testes da API de receções (fatia 2 da recepção de mercadoria)."""


import pytest
from uuid import uuid4
from rest_framework.test import APIClient

from apps.accounts.models import Tenant
from apps.inventory.models import Location
from apps.catalog.models import Supplier
from apps.purchasing.models import Receipt


@pytest.mark.django_db
class TestRececoes:
    """Happy path: criar receção, rever linha, confirmar."""

    def test_criar_rececao_sem_documento(self):
        """POST /receipts sem document: zero linhas, pode acrescentar."""
        tenant = Tenant.objects.create(id=uuid4(), name="Test")
        user = tenant.create_user(email="test@test.com", full_name="Test")
        
        loc = Location.objects.create(tenant=tenant, name="Loja", position=1)
        supplier = Supplier.objects.create(tenant=tenant, name="Fornecedor", nif="987654321")
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        # Criar receção
        data = {
            "location": str(loc.id),
            "supplier_name": "Fornecedor",
            "supplier_nif": "987654321",
            "doc_type": "FT",
            "supplier": str(supplier.id),
        }
        
        response = client.post("/api/v1/receipts", data, format="json")
        assert response.status_code == 201
        receipt_id = response.data["id"]
        
        # Verificar que começa vazio
        response = client.get(f"/api/v1/receipts/{receipt_id}/lines")
        assert response.status_code == 200
        assert response.data["count"] == 0
    
    def test_confirmar_rececao_sem_linhas_revistas_falha(self):
        """POST /receipts/{id}/confirmation sem linhas confirmadas: 409."""
        tenant = Tenant.objects.create(id=uuid4(), name="Test")
        user = tenant.create_user(email="test@test.com", full_name="Test")
        
        loc = Location.objects.create(tenant=tenant, name="Loja", position=1)
        supplier = Supplier.objects.create(tenant=tenant, name="Fornecedor", nif="987654321")
        
        receipt = Receipt.objects.create(
            tenant=tenant,
            location=loc,
            supplier=supplier,
            supplier_name="Fornecedor",
            supplier_nif="987654321",
            doc_type="FT",
        )
        
        client = APIClient()
        client.force_authenticate(user=user)
        
        response = client.post(f"/api/v1/receipts/{receipt.id}/confirmation")
        assert response.status_code == 409
        assert "sem_linhas_revistas" in response.data.get("code", "")
    
    def test_recepcao_outro_tenant_404(self):
        """GET /receipts/{id} de outro tenant: 404."""
        tenant1 = Tenant.objects.create(id=uuid4(), name="Test1")
        tenant2 = Tenant.objects.create(id=uuid4(), name="Test2")
        user1 = tenant1.create_user(email="test1@test.com", full_name="Test1")
        
        loc = Location.objects.create(tenant=tenant1, name="Loja", position=1)
        supplier = Supplier.objects.create(tenant=tenant1, name="Fornecedor", nif="111111111")
        
        receipt = Receipt.objects.create(
            tenant=tenant1,
            location=loc,
            supplier=supplier,
            supplier_name="Fornecedor",
            supplier_nif="111111111",
            doc_type="FT",
        )
        
        client = APIClient()
        client.force_authenticate(user=user1)
        
        response = client.get(f"/api/v1/receipts/{receipt.id}")
        assert response.status_code == 404
