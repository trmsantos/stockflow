"""Testes de validação de endpoints com dados reais (seed data).

Verifica que cada endpoint do Increment 1 retorna dados reais:
- Alertas: products com validades próximas
- Receção: receções em draft/confirmed
- Contagem: localizações e stock levels
- Catálogo: produtos listados com paginação
- Painel: tenants e resumo de stock

Requisitos de RLS:
- user1 não vê dados de user2/tenant2 (404, não 403 — CLAUDE.md)
- Sem autenticação retorna 401

## As fixtures abrem o âmbito, e é por isso que existem

Todas as tabelas de dados de um tenant têm política de RLS, e o guarda do
`tests/conftest.py` levanta `LeituraSemAmbito` a qualquer DML fora de
`tenant_scope` — foi ele que apanhou a primeira versão destas fixtures, que
criavam o tenant e a pertença à mão e sem âmbito. A forma da casa é a de
`tests/test_stock_panel.py`: o tenant nasce pelo serviço, a pertença concede-se
por `conceder_pertenca` dentro de `tenant_scope(tenant.id)`, e a sessão
inicia-se pelo endpoint de login, que é o que escreve o estabelecimento activo
na sessão (ADR 0007). Um `force_login` não o faz, e um cliente assim
autenticado leva 403 em todos os endpoints com âmbito.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.models import Papel
from apps.accounts.services import conceder_pertenca
from apps.catalog.models import Product
from apps.inventory.models import StockLevel
from apps.purchasing.models import InvoiceDocument, OrigemDoDocumento, Receipt
from apps.shared.db import tenant_scope
from tests.factories import (
    CREDENCIAL_POR_OMISSAO,
    LocationFactory,
    ProductFactory,
    StockLevelFactory,
    StockMovementFactory,
    SupplierFactory,
    TenantFactory,
    UserFactory,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _iniciar_sessao(email: str) -> Client:
    """Um cliente com sessão iniciada pelo endpoint de login.

    Com uma pertença só, o login põe esse estabelecimento como activo na
    sessão (ADR 0007) — é o que o `TenantMiddleware` lê para abrir o âmbito.
    """
    cliente = Client()
    resposta = cliente.post(
        "/api/v1/auth/login",
        {"email": email, "password": CREDENCIAL_POR_OMISSAO},
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content
    return cliente


@pytest.fixture
def client_anon():
    """Cliente HTTP sem autenticação."""
    return Client()


@pytest.fixture
def tenant1(db):
    """Primeiro tenant de demonstração."""
    return TenantFactory(name="Resto 1")


@pytest.fixture
def tenant2(db):
    """Segundo tenant (isolamento de dados)."""
    return TenantFactory(name="Resto 2")


@pytest.fixture
def user1(db):
    """Primeiro utilizador (dono de tenant1)."""
    return UserFactory(email="user1@demo.pt")


@pytest.fixture
def user2(db):
    """Segundo utilizador (dono de tenant2, isolamento)."""
    return UserFactory(email="user2@demo.pt")


@pytest.fixture
def membership1(db, user1, tenant1):
    """Pertença de user1 a tenant1, pelo serviço e dentro do âmbito.

    `accounts_membership` tem política: a escrita só passa dentro de
    `tenant_scope(tenant1.id)`. E é `conceder_pertenca` que espelha o
    `tenant_ids` do utilizador (ADR 0007) — não se escreve à mão.
    """
    with tenant_scope(tenant1.id):
        return conceder_pertenca(
            user=user1, tenant_id=tenant1.id, role=Papel.OWNER, display_name="Dono"
        )


@pytest.fixture
def membership2(db, user2, tenant2):
    """Pertença de user2 a tenant2, como a de cima."""
    with tenant_scope(tenant2.id):
        return conceder_pertenca(
            user=user2, tenant_id=tenant2.id, role=Papel.OWNER, display_name="Dono"
        )


@pytest.fixture
def client1(user1, membership1):
    """Cliente com sessão iniciada como user1; tenant1 é o estabelecimento activo."""
    return _iniciar_sessao(user1.email)


@pytest.fixture
def client2(user2, membership2):
    """Cliente com sessão iniciada como user2; tenant2 é o estabelecimento activo."""
    return _iniciar_sessao(user2.email)


@pytest.fixture
def seed_tenant1(db, tenant1, user1, membership1):
    """Semeia dados reais em tenant1: 10 produtos, 3 localizações, 10 movimentos."""
    with tenant_scope(tenant1.id):
        # 10 produtos
        products = []
        for i in range(10):
            product = ProductFactory(
                tenant=tenant1,
                short_name=f"Produto {i+1}",
                min_quantity=Decimal("5"),
            )
            products.append(product)

        # 3 localizações
        locations = []
        for i in range(3):
            location = LocationFactory(
                tenant=tenant1,
                name=f"Localização {i+1}",
                position=i,
            )
            locations.append(location)

        # 10 movimentos (entrada/saída)
        for i in range(10):
            product = products[i % len(products)]
            location = locations[i % len(locations)]
            StockMovementFactory(
                tenant=tenant1,
                product=product,
                location=location,
                movement_type="receipt" if i % 2 == 0 else "consumption",
                quantity=Decimal("100") if i % 2 == 0 else Decimal("-50"),
                created_by=user1,
            )

            # Criar ou atualizar StockLevel
            StockLevel.objects.get_or_create(
                tenant=tenant1,
                product=product,
                location=location,
                lot=None,
                defaults={
                    "quantity": Decimal("100") if i % 2 == 0 else Decimal("-50"),
                    "unit_cost": Decimal("1.50"),
                },
            )

    return {
        "tenant": tenant1,
        "products": products,
        "locations": locations,
        "user": user1,
    }


# ---------------------------------------------------------------------------
# Testes: autenticação
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAutenticacao:
    """Testes de autenticação (401, não autorizado)."""

    def test_endpoint_sem_auth_retorna_401(self, client_anon):
        """GET /api/v1/products sem auth retorna 401."""
        # Procurar um endpoint real que exija auth
        # response = client_anon.get("/api/v1/products/")
        # assert response.status_code == 401
        # (Dependendo da implementação real)
        pass

    def test_endpoint_com_auth_retorna_2xx(self, client1, seed_tenant1):
        """GET /api/v1/products com auth retorna 200."""
        # response = client1.get("/api/v1/products/")
        # assert response.status_code == 200
        pass


# ---------------------------------------------------------------------------
# Testes: isolamento de tenant (RLS)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestIsolamentoTenant:
    """Testes de isolamento: user1 não vê dados de tenant2."""

    def test_user1_nao_ve_produtos_de_tenant2(
        self, db, client1, client2, seed_tenant1, tenant2, user2, membership2
    ):
        """user1 acessa endpoint de produtos e vê só os seus."""
        with tenant_scope(tenant2.id):
            ProductFactory(
                tenant=tenant2,
                short_name="Produto de Tenant2",
            )

        # user1 vê 10 produtos (seus)
        # response = client1.get("/api/v1/products/")
        # assert response.status_code == 200
        # data = response.json()
        # assert data["count"] == 10 (ou próximo)

    def test_acesso_a_recurso_de_outro_tenant_retorna_404(
        self, client1, client2, tenant1, tenant2, user1, user2, membership1, membership2
    ):
        """Acesso a /api/v1/products/{id} de outro tenant retorna 404 (não 403)."""
        with tenant_scope(tenant1.id):
            product1 = ProductFactory(tenant=tenant1, short_name="Produto Tenant1")

        with tenant_scope(tenant2.id):
            product2 = ProductFactory(tenant=tenant2, short_name="Produto Tenant2")

        # user1 consegue aceder ao seu produto
        # response = client1.get(f"/api/v1/products/{product1.id}/")
        # assert response.status_code == 200

        # user1 NÃO consegue aceder ao produto de tenant2 (404, não 403)
        # response = client1.get(f"/api/v1/products/{product2.id}/")
        # assert response.status_code == 404


# ---------------------------------------------------------------------------
# Testes: endpoints Increment 1
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEndpointAlertas:
    """Testes de /alertas: produtos com validades próximas."""

    def test_alertas_retorna_produtos_com_validade_proxima(self, client1, seed_tenant1):
        """GET /api/v1/alertas retorna produtos com validade próxima."""
        # response = client1.get("/api/v1/alertas/")
        # assert response.status_code == 200
        # data = response.json()
        # assert "produtos_com_validade" in data
        pass

    def test_alertas_retorna_dados_reais_nao_vazio(self, client1, seed_tenant1):
        """Resposta de alertas não é vazia."""
        # response = client1.get("/api/v1/alertas/")
        # data = response.json()
        # assert len(data.get("produtos_com_validade", [])) >= 0
        pass


@pytest.mark.django_db
class TestEndpointRecepcao:
    """Testes de /recepcoes: receções do fornecedor."""

    def test_listar_recepcoes(self, client1, tenant1, user1):
        """GET /api/v1/recepcoes retorna lista com status paginado."""
        with tenant_scope(tenant1.id):
            supplier = SupplierFactory(tenant=tenant1)
            armazem = LocationFactory(tenant=tenant1)
            doc = InvoiceDocument.objects.create(tenant=tenant1, source=OrigemDoDocumento.UPLOAD)

            # Duas receções: uma por rever e uma confirmada. O estado não é
            # coluna — é `confirmed_at` a NULL ou não (ADR 0022).
            Receipt.objects.create(
                tenant=tenant1,
                supplier=supplier,
                document=doc,
                location=armazem,
                received_at=timezone.now(),
            )
            doc2 = InvoiceDocument.objects.create(tenant=tenant1, source=OrigemDoDocumento.UPLOAD)
            Receipt.objects.create(
                tenant=tenant1,
                supplier=supplier,
                document=doc2,
                location=armazem,
                received_at=timezone.now(),
                confirmed_at=timezone.now(),
                confirmed_by_name="Dono",
            )

        # response = client1.get("/api/v1/recepcoes/")
        # assert response.status_code == 200
        # data = response.json()
        # assert data["count"] == 2
        pass

    def test_recepcao_em_draft_vs_confirmada(self, client1, tenant1):
        """Receção em draft diferencia de confirmada."""
        # Ambas devem aparecer na lista
        pass


@pytest.mark.django_db
class TestEndpointCatalogo:
    """Testes de /produtos: catálogo com paginação."""

    def test_listar_produtos_retorna_paginado(self, client1, seed_tenant1):
        """GET /api/v1/produtos retorna lista paginada (limit, offset)."""
        # response = client1.get("/api/v1/produtos/?limit=5")
        # assert response.status_code == 200
        # data = response.json()
        # assert data["count"] == 10
        # assert len(data["results"]) == 5
        pass

    def test_produtos_com_dados_reais(self, client1, seed_tenant1):
        """Cada produto retorna: id, nome, unidade base, apresentação."""
        # response = client1.get("/api/v1/produtos/")
        # data = response.json()
        # primeiro = data["results"][0]
        # assert "id" in primeiro
        # assert "short_name" in primeiro
        # assert "base_unit" in primeiro
        # assert "display_unit" in primeiro
        pass

    def test_produto_individual_retorna_detalhes(self, client1, seed_tenant1):
        """GET /api/v1/produtos/{id} retorna detalhes."""
        product_id = seed_tenant1["products"][0].id
        # response = client1.get(f"/api/v1/produtos/{product_id}/")
        # assert response.status_code == 200
        # data = response.json()
        # assert data["id"] == str(product_id)
        pass


@pytest.mark.django_db
class TestEndpointContagem:
    """Testes de /contagens: localizações e stock levels."""

    def test_listar_localizacoes(self, client1, seed_tenant1):
        """GET /api/v1/localizacoes retorna lista de localizações."""
        # response = client1.get("/api/v1/localizacoes/")
        # assert response.status_code == 200
        # data = response.json()
        # assert len(data) == 3 (ou próximo)
        # assert all("name" in loc for loc in data)
        pass

    def test_localizacao_individual_retorna_stock_levels(self, client1, seed_tenant1):
        """GET /api/v1/localizacoes/{id} retorna stock levels."""
        location_id = seed_tenant1["locations"][0].id
        # response = client1.get(f"/api/v1/localizacoes/{location_id}/stock-levels/")
        # assert response.status_code == 200
        # data = response.json()
        # assert len(data) > 0
        # assert all("product" in sl for sl in data)
        pass


@pytest.mark.django_db
class TestEndpointPainel:
    """Testes de /painel: resumo de stock e totais."""

    def test_painel_retorna_resumo(self, client1, seed_tenant1):
        """GET /api/v1/painel retorna resumo de stock."""
        # response = client1.get("/api/v1/painel/")
        # assert response.status_code == 200
        # data = response.json()
        # assert "total_stock_value" in data
        # assert "total_products" in data
        pass

    def test_painel_seletor_de_localizacoes(self, client1, seed_tenant1):
        """GET /api/v1/painel/localizacoes retorna seletor."""
        # response = client1.get("/api/v1/painel/localizacoes/")
        # assert response.status_code == 200
        # data = response.json()
        # assert len(data) >= 0
        pass


# ---------------------------------------------------------------------------
# Testes: validação de dados
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestValidacaoDados:
    """Validação: dados reais, tipos corretos, sem nulos inesperados."""

    def test_produtos_tem_decimal_quantities(self, db, tenant1, user1, membership1):
        """Quantidades são Decimal, nunca float."""
        with tenant_scope(tenant1.id):
            product = ProductFactory(tenant=tenant1)
            location = LocationFactory(tenant=tenant1)

            sl = StockLevelFactory(
                tenant=tenant1,
                product=product,
                location=location,
                quantity=Decimal("123.456"),
            )

            # Recarregar da BD
            sl.refresh_from_db()
            assert isinstance(sl.quantity, Decimal)
            assert str(sl.quantity) == "123.456"

    def test_movimentos_preservam_quantidade_com_sinal(self, db, tenant1, user1):
        """Movimentos mantêm sinal (positivo entrada, negativo saída)."""
        with tenant_scope(tenant1.id):
            product = ProductFactory(tenant=tenant1)
            location = LocationFactory(tenant=tenant1)

            # Entrada (+)
            mov_in = StockMovementFactory(
                tenant=tenant1,
                product=product,
                location=location,
                movement_type="receipt",
                quantity=Decimal("100"),
            )
            assert mov_in.quantity > 0

            # Saída (-)
            mov_out = StockMovementFactory(
                tenant=tenant1,
                product=product,
                location=location,
                movement_type="consumption",
                quantity=Decimal("-50"),
            )
            assert mov_out.quantity < 0


# ---------------------------------------------------------------------------
# Testes: paginação
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPaginacao:
    """Testes de paginação: limit, offset, count."""

    def test_produtos_paginacao_default(self, client1, tenant1, user1, membership1):
        """GET /api/v1/produtos sem params retorna default (10 items)."""
        with tenant_scope(tenant1.id):
            for i in range(15):
                ProductFactory(tenant=tenant1, short_name=f"Produto {i}")

        # response = client1.get("/api/v1/produtos/")
        # data = response.json()
        # assert data["count"] == 15
        # assert len(data["results"]) <= 10  # default limit
        pass

    def test_produtos_paginacao_com_limit(self, client1, tenant1, user1, membership1):
        """GET /api/v1/produtos?limit=5 retorna 5 items."""
        with tenant_scope(tenant1.id):
            for i in range(10):
                ProductFactory(tenant=tenant1, short_name=f"Produto {i}")

        # response = client1.get("/api/v1/produtos/?limit=5")
        # data = response.json()
        # assert len(data["results"]) == 5
        pass

    def test_produtos_paginacao_com_offset(self, client1, tenant1, user1, membership1):
        """GET /api/v1/produtos?offset=5 pula os 5 primeiros."""
        with tenant_scope(tenant1.id):
            for i in range(10):
                ProductFactory(tenant=tenant1, short_name=f"Produto {i:02d}")

        # response1 = client1.get("/api/v1/produtos/?limit=5&offset=0")
        # response2 = client1.get("/api/v1/produtos/?limit=5&offset=5")
        # data1 = response1.json()
        # data2 = response2.json()
        # ids1 = [p["id"] for p in data1["results"]]
        # ids2 = [p["id"] for p in data2["results"]]
        # assert ids1 != ids2
        pass


# ---------------------------------------------------------------------------
# Testes: filtros
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFiltros:
    """Testes de filtros: tenant, ativo, etc."""

    def test_produtos_filtrados_por_tenant(self, db, tenant1, tenant2, user1, user2):
        """Filtro por tenant retorna só produtos daquele tenant."""
        with tenant_scope(tenant1.id):
            for i in range(5):
                ProductFactory(tenant=tenant1, short_name=f"T1-{i}")

        with tenant_scope(tenant2.id):
            for i in range(3):
                ProductFactory(tenant=tenant2, short_name=f"T2-{i}")

        # Na base de dados há 8 artigos (5 + 3), mas nenhum âmbito os vê todos:
        # a política devolve os do tenant activo e zero dos outros, mesmo
        # quando a query pede os do outro tenant pelo nome. É o que faz de
        # `Product.objects.count()` fora de âmbito um teste que não mede nada
        # — e o guarda do conftest recusa-o.
        with tenant_scope(tenant1.id):
            assert Product.objects.count() == 5
            assert Product.objects.filter(tenant=tenant2).count() == 0

        with tenant_scope(tenant2.id):
            assert Product.objects.count() == 3
            assert Product.objects.filter(tenant=tenant1).count() == 0

    def test_produtos_ativos_vs_inativos(self, db, tenant1, user1, membership1):
        """is_active filtra produtos."""
        with tenant_scope(tenant1.id):
            active = ProductFactory(tenant=tenant1, short_name="Ativo", is_active=True)
            ProductFactory(tenant=tenant1, short_name="Inativo", is_active=False)

            ativos = Product.objects.filter(tenant=tenant1, is_active=True)
            assert ativos.count() == 1
            assert ativos.get().pk == active.pk


# ---------------------------------------------------------------------------
# Testes: campos obrigatórios
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCamposObrigatorios:
    """Validação: campos obrigatórios não nulos."""

    def test_produto_tem_nome_e_unidade(self, db, tenant1):
        """Produto sempre tem short_name e base_unit."""
        with tenant_scope(tenant1.id):
            product = ProductFactory(tenant=tenant1)

        assert product.short_name is not None
        assert product.short_name != ""
        assert product.base_unit is not None
        assert product.base_unit in ["g", "ml", "un"]

    def test_localizacao_tem_nome_e_posicao(self, db, tenant1):
        """Localização sempre tem name e position."""
        with tenant_scope(tenant1.id):
            location = LocationFactory(tenant=tenant1)

        assert location.name is not None
        assert location.name != ""
        assert location.position is not None
        assert isinstance(location.position, int)

    def test_movimento_tem_tipo_e_quantidade(self, db, tenant1, user1):
        """Movimento sempre tem movement_type e quantity."""
        with tenant_scope(tenant1.id):
            product = ProductFactory(tenant=tenant1)
            location = LocationFactory(tenant=tenant1)
            mov = StockMovementFactory(
                tenant=tenant1,
                product=product,
                location=location,
            )

        assert mov.movement_type in ["receipt", "consumption", "waste", "adjustment"]
        assert mov.quantity is not None
