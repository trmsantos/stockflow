"""Testes da API de receções (fatia 2 da recepção de mercadoria)."""

from decimal import Decimal
from unittest import mock

import pytest
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Papel, User
from apps.accounts.services import conceder_pertenca, criar_tenant
from apps.catalog.models import Product, Supplier, UnidadeBase
from apps.inventory.models import Location
from apps.purchasing import services, views
from apps.purchasing.models import Receipt, ReceiptLine
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

    def test_listar_rececoes_devolve_pagina_com_rececoes_compostas(self):
        """GET /receipts — 200, forma paginada do DRF e cada receção já composta."""
        tenant = criar_tenant(name="Test Lista")

        with tenant_scope(tenant.id):
            user = User.objects.create_user("lista@test.com", CREDENCIAL)
            conceder_pertenca(user=user, tenant_id=tenant.id, role=Papel.OWNER, display_name="Test")
            loc = Location.objects.create(tenant=tenant, name="Loja", position=1)
            supplier = Supplier.objects.create(tenant=tenant, name="Fornecedor", nif="987654321")
            receipt = Receipt.objects.create(
                tenant=tenant,
                location=loc,
                supplier=supplier,
                supplier_name="Fornecedor",
                supplier_nif="987654321",
                doc_type="FT",
                received_at=timezone.now(),
            )

        client = Client()
        response = client.post(
            "/api/v1/auth/login",
            {"email": "lista@test.com", "password": CREDENCIAL},
            content_type="application/json",
        )
        assert response.status_code == 200
        api_client = APIClient()
        for key, value in response.cookies.items():
            api_client.cookies[key] = value.value

        response = api_client.get("/api/v1/receipts")
        assert response.status_code == 200
        assert response.data["count"] == 1
        linha = response.data["results"][0]
        assert linha["id"] == str(receipt.id)
        assert linha["status"] == "needs_review"
        assert linha["supplier"] == {"name": "Fornecedor", "nif": "987654321"}

        response = api_client.get("/api/v1/receipts?estado=revisao")
        assert response.status_code == 200
        assert [r["id"] for r in response.data["results"]] == [str(receipt.id)]

        response = api_client.get("/api/v1/receipts?estado=hoje")
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


# ---------------------------------------------------------------------------
# Os euros de uma receção são de `owner|manager` (decisão do dono, 2026-10-19)
#
# Os endpoints de receção continuam sem `TemPapel` (ADR 0021, decisão 9):
# receber mercadoria é trabalho de quem está lá. O que mudou é o dinheiro — até
# à fatia da extração (ADR 0031) uma receção nascia sem linhas e não havia euros
# lá dentro; desde que o `criar_rececao` as semeia a partir da fatura, um
# colaborador via os preços de compra de um documento inteiro.
#
# O que estes testes afirmam é a **ausência da chave** e nunca um zero nem um
# `null`: é o reflexo do `_dinheiro` do porto do `agents`. Um `assert
# resposta["unit_price"] is None` passaria com a fuga meio tapada.
# ---------------------------------------------------------------------------

#: As chaves de dinheiro de uma linha e de um cabeçalho de receção.
EUROS_DA_LINHA = ("unit_price", "discount_pct", "line_total", "price_history")
EUROS_DA_RECECAO = ("document_total", "lines_total", "vat_breakdown")


def _loja_com_rececao_com_precos(nome: str):
    """Um estabelecimento com um gerente, um colaborador e uma receção com euros."""
    tenant = criar_tenant(name=nome)
    with tenant_scope(tenant.id):
        gerente = User.objects.create_user(f"gerente-{nome}@test.com", CREDENCIAL)
        conceder_pertenca(
            user=gerente, tenant_id=tenant.id, role=Papel.MANAGER, display_name="Gerente"
        )
        colaborador = User.objects.create_user(f"staff-{nome}@test.com", CREDENCIAL)
        conceder_pertenca(
            user=colaborador, tenant_id=tenant.id, role=Papel.STAFF, display_name="Colaborador"
        )
        loc = Location.objects.create(tenant=tenant, name="Armazém", position=1)
        fornecedor = Supplier.objects.create(tenant=tenant, name="Makro", nif="987654321")
        rececao = Receipt.objects.create(
            tenant=tenant,
            location=loc,
            supplier=fornecedor,
            supplier_name="Makro",
            supplier_nif="987654321",
            doc_type="FT",
            received_at=timezone.now(),
            document_total_eur=Decimal("123.45"),
        )
        linha = ReceiptLine.objects.create(
            tenant=tenant,
            receipt=rececao,
            location=loc,
            position=1,
            description="Manteiga 1 kg",
            invoice_unit="un",
            quantity_invoiced=Decimal("10.000"),
            quantity_received=Decimal("10.000"),
            unit_price=Decimal("9.4000"),
            discount_pct=Decimal("5.000"),
            vat_rate=Decimal("23.000"),
            line_total=Decimal("100.00"),
            kind="charge",
        )
    return tenant, loc, linha, rececao


def _sessao(email: str) -> APIClient:
    """Faz login e devolve um cliente com os cookies da sessão."""
    resposta = Client().post(
        "/api/v1/auth/login",
        {"email": email, "password": CREDENCIAL},
        content_type="application/json",
    )
    assert resposta.status_code == 200
    api_client = APIClient()
    for chave, valor in resposta.cookies.items():
        api_client.cookies[chave] = valor.value
    return api_client


@pytest.mark.django_db(transaction=True)
class TestEurosDeUmaRececao:
    """Só `owner|manager` veem dinheiro numa receção; o resto do trabalho é de todos."""

    def test_o_colaborador_nao_recebe_as_chaves_de_dinheiro(self):
        """GET /receipts/{id} e /lines: sem `unit_price`, `line_total`, totais."""
        _, _, _, rececao = _loja_com_rececao_com_precos("sem-euros")
        api = _sessao("staff-sem-euros@test.com")

        detalhe = api.get(f"/api/v1/receipts/{rececao.id}")
        assert detalhe.status_code == 200
        for chave in EUROS_DA_RECECAO:
            assert chave not in detalhe.data, chave

        linhas = api.get(f"/api/v1/receipts/{rececao.id}/lines")
        assert linhas.status_code == 200
        assert linhas.data["count"] == 1
        for chave in EUROS_DA_LINHA:
            assert chave not in linhas.data["results"][0], chave

    def test_o_colaborador_continua_a_ver_o_que_precisa_para_receber(self):
        """A quantidade, a unidade, a taxa de IVA e os avisos não são dinheiro."""
        _, _, _, rececao = _loja_com_rececao_com_precos("trabalho")
        api = _sessao("staff-trabalho@test.com")

        linha = api.get(f"/api/v1/receipts/{rececao.id}/lines").data["results"][0]
        assert linha["quantity_received"] == "10.000"
        assert linha["invoice_unit"] == "un"
        assert linha["vat_rate"] == "23.000"
        assert "warnings" in linha

    def test_o_gerente_recebe_as_chaves_de_dinheiro(self):
        """O mesmo pedido, com papel de gerente: os euros estão lá."""
        _, _, _, rececao = _loja_com_rececao_com_precos("com-euros")
        api = _sessao("gerente-com-euros@test.com")

        detalhe = api.get(f"/api/v1/receipts/{rececao.id}")
        assert detalhe.status_code == 200
        assert detalhe.data["document_total"] == "123.45"
        assert detalhe.data["lines_total"] == "100.00"
        assert detalhe.data["vat_breakdown"][0]["rate"] == "23.000"

        linhas = api.get(f"/api/v1/receipts/{rececao.id}/lines")
        assert linhas.data["results"][0]["unit_price"] == "9.4000"
        assert linhas.data["results"][0]["line_total"] == "100.00"
        assert linhas.data["results"][0]["discount_pct"] == "5.000"

    def test_a_listagem_segue_a_mesma_regra(self):
        """GET /receipts: a página do colaborador não traz totais; a do gerente traz."""
        _, _, _, rececao = _loja_com_rececao_com_precos("listagem")

        pagina = _sessao("staff-listagem@test.com").get("/api/v1/receipts")
        assert pagina.status_code == 200
        assert pagina.data["count"] == 1
        for chave in EUROS_DA_RECECAO:
            assert chave not in pagina.data["results"][0], chave

        pagina = _sessao("gerente-listagem@test.com").get("/api/v1/receipts")
        assert pagina.data["results"][0]["document_total"] == "123.45"

    def test_o_201_de_criar_uma_rececao_nao_traz_o_total_ao_colaborador(self):
        """A escrita devolve o estado completo — e o completo dele não tem euros."""
        tenant, loc, _, _ = _loja_com_rececao_com_precos("criacao")
        corpo = {
            "location": str(loc.id),
            "supplier_name": "Makro",
            "doc_type": "FT",
            "document_total_eur": "77.70",
        }

        criada = _sessao("staff-criacao@test.com").post(
            "/api/v1/receipts", corpo, format="json"
        )
        assert criada.status_code == 201
        for chave in EUROS_DA_RECECAO:
            assert chave not in criada.data, chave

        criada = _sessao("gerente-criacao@test.com").post(
            "/api/v1/receipts", corpo, format="json"
        )
        assert criada.status_code == 201
        assert criada.data["document_total"] == "77.70"

    def test_o_201_da_revisao_de_uma_linha_nao_traz_o_preco_ao_colaborador(self):
        """Marcar uma linha é trabalho dele; o preço da linha marcada não é."""
        _, _, linha, rececao = _loja_com_rececao_com_precos("revisao")
        caminho = f"/api/v1/receipts/{rececao.id}/lines/{linha.id}/confirmation"
        corpo = {"kind": "charge", "quantity_received": "10.000"}

        revista = _sessao("staff-revisao@test.com").post(caminho, corpo, format="json")
        assert revista.status_code == 201
        assert revista.data["status"] == "confirmed"
        for chave in EUROS_DA_LINHA:
            assert chave not in revista.data, chave

        revista = _sessao("gerente-revisao@test.com").post(caminho, corpo, format="json")
        assert revista.status_code == 201
        assert revista.data["line_total"] == "100.00"


# ---------------------------------------------------------------------------
# Acrescentar uma linha à mão: `POST /receipts/<id>/lines`
#
# O caminho de quem tem a fatura na mão e vê que falta uma linha. Respondia
# **500** a todos os pedidos, e a causa não era a localização em si: o contrato
# diz `product`, `packaging` e `location`, as colunas chamam-se `*_id`, e este
# serializer era o único dos quatro de entrada deste módulo sem a tradução. A
# view entregava o `validated_data` ao Django, que recusa um `UUID` onde a
# descritora de uma chave estrangeira quer uma instância.
#
# O resto do que estes testes fixam é o que estava por decidir **por baixo** do
# 500 e só aparece quando ele desaparece: a posição, as duas colunas `NOT NULL`
# que o contrato deixa opcionais, e a receção já confirmada.
# ---------------------------------------------------------------------------


def _loja_com_rececao_por_rever(nome: str):
    """Um estabelecimento com um gerente, um colaborador e uma receção vazia."""
    tenant = criar_tenant(name=nome)
    with tenant_scope(tenant.id):
        gerente = User.objects.create_user(f"gerente-{nome}@test.com", CREDENCIAL)
        conceder_pertenca(
            user=gerente, tenant_id=tenant.id, role=Papel.MANAGER, display_name="Gerente"
        )
        colaborador = User.objects.create_user(f"staff-{nome}@test.com", CREDENCIAL)
        conceder_pertenca(
            user=colaborador, tenant_id=tenant.id, role=Papel.STAFF, display_name="Colaborador"
        )
        loc = Location.objects.create(tenant=tenant, name="Armazém", position=1)
        outra = Location.objects.create(tenant=tenant, name="Câmara", position=2)
        fornecedor = Supplier.objects.create(tenant=tenant, name="Makro", nif="987654321")
        rececao = Receipt.objects.create(
            tenant=tenant,
            location=loc,
            supplier=fornecedor,
            supplier_name="Makro",
            supplier_nif="987654321",
            doc_type="FT",
            received_at=timezone.now(),
        )
    return tenant, loc, outra, rececao


#: O corpo mínimo de uma linha acrescentada à mão: o que o papel diz.
LINHA_A_MAO = {
    "description": "FARINHA T65 25KG",
    "invoice_unit": "SC",
    "quantity_invoiced": "2.000",
    "unit_price": "17.3300",
    "line_total": "34.66",
    "vat_rate": "6.000",
}


@pytest.mark.django_db(transaction=True)
class TestAcrescentarLinhaAMao:
    """`POST /receipts/<id>/lines` — o caminho central que respondia 500."""

    def test_acrescentar_uma_linha_devolve_201_e_ela_nasce_por_rever(self):
        """O pedido que dava 500. A linha nasce `needs_review`, como as semeadas."""
        _, loc, _, rececao = _loja_com_rececao_por_rever("a-mao")
        api = _sessao("gerente-a-mao@test.com")

        criada = api.post(
            f"/api/v1/receipts/{rececao.id}/lines",
            {**LINHA_A_MAO, "location": str(loc.id), "quantity_received": "50000.000"},
            format="json",
        )

        assert criada.status_code == 201, criada.data
        assert criada.data["description"] == "FARINHA T65 25KG"
        assert criada.data["position"] == 1
        assert criada.data["status"] == "needs_review"
        assert criada.data["reviewed_at"] is None
        assert criada.data["quantity_received"] == "50000.000"
        assert criada.data["location"]["id"] == str(loc.id)

        linhas = api.get(f"/api/v1/receipts/{rececao.id}/lines")
        assert linhas.data["count"] == 1

    def test_a_linha_sem_localizacao_herda_a_da_rececao(self):
        """A coluna é `NOT NULL` e o campo é opcional: o default é um facto.

        A localização da receção é a mesma que o `_semear_linhas` escreve nas
        linhas lidas da fatura, e é a única que não é um palpite. Sem isto, o
        pedido que o contrato diz ser válido dava um segundo 500 — agora do
        Postgres, por violação de `NOT NULL`.
        """
        _, loc, _, rececao = _loja_com_rececao_por_rever("sem-local")
        api = _sessao("gerente-sem-local@test.com")

        criada = api.post(
            f"/api/v1/receipts/{rececao.id}/lines", LINHA_A_MAO, format="json"
        )

        assert criada.status_code == 201, criada.data
        assert criada.data["location"]["id"] == str(loc.id)

    def test_a_linha_sem_quantidade_recebida_nao_inventa_nenhuma(self):
        """Sem conversão conhecida, zero — **nunca** um factor 1 implícito.

        É a regra do `_quantidade_recebida`, a mesma da sementeira (ADR 0022). A
        coluna também é `NOT NULL`, logo a alternativa a decidir isto aqui era o
        terceiro 500 do mesmo endpoint.
        """
        _, _, _, rececao = _loja_com_rececao_por_rever("sem-qtd")
        api = _sessao("gerente-sem-qtd@test.com")

        sem_factor = api.post(
            f"/api/v1/receipts/{rececao.id}/lines", LINHA_A_MAO, format="json"
        )
        com_factor = api.post(
            f"/api/v1/receipts/{rececao.id}/lines",
            {**LINHA_A_MAO, "base_per_invoice_unit": "25000.000"},
            format="json",
        )

        assert sem_factor.status_code == 201, sem_factor.data
        assert sem_factor.data["quantity_received"] == "0.000"
        assert com_factor.status_code == 201, com_factor.data
        assert com_factor.data["quantity_received"] == "50000.000"

    def test_o_artigo_e_a_embalagem_tambem_atravessam_pelo_nome_do_contrato(self):
        """Os outros dois campos da mesma tradução, para a correcção ser a regra.

        `product` e `packaging` davam o mesmo `ValueError` do `location` — o que
        os salvava de aparecer era serem opcionais e ninguém os mandar.
        """
        from apps.catalog.models import Product, ProductPackaging, UnidadeBase

        tenant, _, _, rececao = _loja_com_rececao_por_rever("com-artigo")
        with tenant_scope(tenant.id):
            artigo = Product.objects.create(
                tenant=tenant,
                short_name="Farinha T65",
                sku="FAR65",
                base_unit=UnidadeBase.GRAMA,
                display_unit="kg",
                display_factor=Decimal("1000"),
            )
            saco = ProductPackaging.objects.create(
                tenant=tenant, product=artigo, label="saco 25 kg",
                base_quantity=Decimal("25000"),
            )
        api = _sessao("gerente-com-artigo@test.com")

        criada = api.post(
            f"/api/v1/receipts/{rececao.id}/lines",
            {**LINHA_A_MAO, "product": str(artigo.id), "packaging": str(saco.id)},
            format="json",
        )

        assert criada.status_code == 201, criada.data
        assert criada.data["product"] == str(artigo.id)
        assert criada.data["packaging"]["id"] == str(saco.id)

    def test_duas_linhas_seguidas_nao_colidem_na_posicao(self):
        """A posição é densa e sai do máximo, sob o lock da receção."""
        _, _, _, rececao = _loja_com_rececao_por_rever("posicoes")
        api = _sessao("gerente-posicoes@test.com")
        caminho = f"/api/v1/receipts/{rececao.id}/lines"

        primeira = api.post(caminho, LINHA_A_MAO, format="json")
        segunda = api.post(
            caminho, {**LINHA_A_MAO, "description": "AÇÚCAR 1KG"}, format="json"
        )

        assert [primeira.status_code, segunda.status_code] == [201, 201]
        assert [primeira.data["position"], segunda.data["position"]] == [1, 2]

    def test_uma_rececao_confirmada_nao_recebe_mais_linhas(self):
        """409. Uma linha nova numa receção já no ledger nunca seria confirmada."""
        tenant, _, _, rececao = _loja_com_rececao_por_rever("confirmada")
        with tenant_scope(tenant.id):
            Receipt.objects.filter(pk=rececao.id).update(
                confirmed_at=timezone.now(), updated_at=timezone.now()
            )
        api = _sessao("gerente-confirmada@test.com")

        recusa = api.post(
            f"/api/v1/receipts/{rececao.id}/lines", LINHA_A_MAO, format="json"
        )

        assert recusa.status_code == 409
        assert recusa.data["code"] == "rececao_confirmada"
        with tenant_scope(tenant.id):
            assert ReceiptLine.objects.filter(receipt_id=rececao.id).count() == 0

    def test_a_rececao_de_outro_estabelecimento_da_404(self):
        """404 e não 403: a linha não é legível, logo não há objecto a negar."""
        _, _, _, alheia = _loja_com_rececao_por_rever("alheia")
        _loja_com_rececao_por_rever("propria")
        api = _sessao("gerente-propria@test.com")

        resposta = api.post(
            f"/api/v1/receipts/{alheia.id}/lines", LINHA_A_MAO, format="json"
        )

        assert resposta.status_code == 404

    def test_o_201_da_linha_acrescentada_nao_traz_os_euros_ao_colaborador(self):
        """Acrescentar a linha é trabalho dele; o preço que ela leva não é.

        O corpo **de entrada** continua a aceitar o preço — quem tem a fatura na
        mão copia-o —, e o que não volta na resposta são os euros.
        """
        _, _, _, rececao = _loja_com_rececao_por_rever("euros-a-mao")
        caminho = f"/api/v1/receipts/{rececao.id}/lines"

        criada = _sessao("staff-euros-a-mao@test.com").post(
            caminho, LINHA_A_MAO, format="json"
        )
        assert criada.status_code == 201, criada.data
        for chave in EUROS_DA_LINHA:
            assert chave not in criada.data, chave

        criada = _sessao("gerente-euros-a-mao@test.com").post(
            caminho, LINHA_A_MAO, format="json"
        )
        assert criada.status_code == 201
        assert criada.data["unit_price"] == "17.3300"
        assert criada.data["line_total"] == "34.66"


# ---------------------------------------------------------------------------
# Confirmar uma linha: `POST /receipts/<id>/lines/<linha>/confirmation`
#
# O portão humano da extração (ADR 0031) é este endpoint, e ele respondia
# **500** ao gesto mais provável da fatia: a primeira fatura de um fornecedor
# novo semeia linhas `kind=goods` **sem artigo** — a correspondência é por chave
# exacta (`supplier_id`, `code`) e não há correspondência difusa por descrição
# (ADR 0031, decisão 5) —, e quem carregasse em confirmar antes de escolher o
# artigo levava um erro de servidor em vez de uma frase.
#
# O que estes testes fixam é a tradução de cada exceção de domínio que este
# caminho levanta: `SemArtigo` em 400 com a frase, e a `RececaoConfirmada` que
# o serviço levanta quando a receção é confirmada **entre** a verificação da
# view e a escrita — a corrida que a verificação da view não fecha.
# ---------------------------------------------------------------------------


def _corrida_que_confirma(rececao_id, servico):
    """O serviço real, com a receção a ser confirmada mesmo antes de ele correr.

    É a corrida a sério e não um duplo: a confirmação acontece **dentro** do
    pedido, depois de a view já ter lido a receção por rever, e quem levanta é o
    serviço verdadeiro ao reler a linha. Sem isto, a segunda rede do
    `line_confirmation` e do `destroy` não é exercida por teste nenhum — e era
    por não ser exercida que ela não existia.
    """

    def servico_com_corrida(**kwargs):
        Receipt.objects.filter(pk=rececao_id).update(
            confirmed_at=timezone.now(), updated_at=timezone.now()
        )
        return servico(**kwargs)

    return servico_com_corrida


@pytest.mark.django_db(transaction=True)
class TestConfirmarUmaLinha:
    """`POST /receipts/<id>/lines/<linha>/confirmation` — o portão humano."""

    def test_a_linha_de_mercadoria_sem_artigo_recusa_com_400_e_diz_o_que_fazer(self):
        """O pedido que dava 500. 400, `code` para ramificar e frase para ler."""
        tenant, _, _, rececao = _loja_com_rececao_por_rever("sem-artigo")
        api = _sessao("gerente-sem-artigo@test.com")
        linha = api.post(
            f"/api/v1/receipts/{rececao.id}/lines", LINHA_A_MAO, format="json"
        )
        assert linha.status_code == 201, linha.data

        recusa = api.post(
            f"/api/v1/receipts/{rececao.id}/lines/{linha.data['id']}/confirmation",
            {"kind": "goods"},
            format="json",
        )

        assert recusa.status_code == 400, recusa.data
        assert recusa.data["code"] == "linha_sem_artigo"
        assert recusa.data["detail"] == (
            "Escolha o artigo desta linha antes de a confirmar, ou deixe a "
            "linha fora desta entrada."
        )
        with tenant_scope(tenant.id):
            assert ReceiptLine.objects.get(pk=linha.data["id"]).status == "needs_review"

    def test_o_corpo_vazio_de_uma_linha_de_mercadoria_recusa_na_mesma(self):
        """Sem `kind`, a linha é mercadoria: o «confirmo» de um corpo vazio recusa."""
        _, _, _, rececao = _loja_com_rececao_por_rever("vazio-sem-artigo")
        api = _sessao("gerente-vazio-sem-artigo@test.com")
        linha = api.post(
            f"/api/v1/receipts/{rececao.id}/lines", LINHA_A_MAO, format="json"
        )

        recusa = api.post(
            f"/api/v1/receipts/{rececao.id}/lines/{linha.data['id']}/confirmation",
            {},
            format="json",
        )

        assert recusa.status_code == 400, recusa.data
        assert recusa.data["code"] == "linha_sem_artigo"

    def test_a_linha_de_mercadoria_com_artigo_continua_a_confirmar(self):
        """O caminho feliz não muda: com artigo escolhido, 201 e `confirmed`."""
        tenant, _, _, rececao = _loja_com_rececao_por_rever("com-artigo-confirma")
        with tenant_scope(tenant.id):
            artigo = Product.objects.create(
                tenant=tenant,
                short_name="Farinha T65",
                sku="FAR65",
                base_unit=UnidadeBase.GRAMA,
                display_unit="kg",
                display_factor=Decimal("1000"),
            )
        api = _sessao("gerente-com-artigo-confirma@test.com")
        linha = api.post(
            f"/api/v1/receipts/{rececao.id}/lines", LINHA_A_MAO, format="json"
        )

        revista = api.post(
            f"/api/v1/receipts/{rececao.id}/lines/{linha.data['id']}/confirmation",
            {
                "kind": "goods",
                "product": str(artigo.id),
                "base_per_invoice_unit": "25000.000",
            },
            format="json",
        )

        assert revista.status_code == 201, revista.data
        assert revista.data["status"] == "confirmed"
        assert revista.data["product"] == str(artigo.id)
        assert revista.data["quantity_received"] == "50000.000"

    def test_o_que_nao_e_mercadoria_confirma_se_sem_artigo_nenhum(self):
        """Um encargo não tem artigo e nunca teve de ter — e continua a passar.

        Vasilhame, portes e descontos de rodapé não geram movimento (ADR 0021,
        decisão 6): exigir-lhes um artigo era inventar uma entrada no catálogo
        para uma linha que não entra em stock.
        """
        _, _, _, rececao = _loja_com_rececao_por_rever("encargo")
        api = _sessao("gerente-encargo@test.com")
        linha = api.post(
            f"/api/v1/receipts/{rececao.id}/lines",
            {**LINHA_A_MAO, "description": "PORTES", "kind": "charge"},
            format="json",
        )

        revista = api.post(
            f"/api/v1/receipts/{rececao.id}/lines/{linha.data['id']}/confirmation",
            {"kind": "charge"},
            format="json",
        )

        assert revista.status_code == 201, revista.data
        assert revista.data["status"] == "confirmed"
        assert revista.data["product"] is None

    def test_a_linha_deixada_de_fora_nao_precisa_de_artigo(self):
        """`skip` é a saída que a frase da recusa oferece: fica fora da entrada."""
        _, _, _, rececao = _loja_com_rececao_por_rever("de-fora")
        api = _sessao("gerente-de-fora@test.com")
        linha = api.post(
            f"/api/v1/receipts/{rececao.id}/lines", LINHA_A_MAO, format="json"
        )

        revista = api.post(
            f"/api/v1/receipts/{rececao.id}/lines/{linha.data['id']}/confirmation",
            {"skip": True, "kind": "deposit"},
            format="json",
        )

        assert revista.status_code == 201, revista.data
        assert revista.data["status"] == "skipped"

    def test_a_rececao_confirmada_a_meio_do_pedido_da_409_e_nao_500(self):
        """A segunda rede: quem confirma a receção entre a leitura e a escrita."""
        tenant, _, _, rececao = _loja_com_rececao_por_rever("corrida-revisao")
        api = _sessao("gerente-corrida-revisao@test.com")
        linha = api.post(
            f"/api/v1/receipts/{rececao.id}/lines", LINHA_A_MAO, format="json"
        )
        caminho = f"/api/v1/receipts/{rececao.id}/lines/{linha.data['id']}/confirmation"

        with mock.patch.object(
            views, "rever_linha", _corrida_que_confirma(rececao.id, services.rever_linha)
        ):
            recusa = api.post(caminho, {"kind": "charge"}, format="json")

        assert recusa.status_code == 409, recusa.data
        assert recusa.data["code"] == "rececao_confirmada"
        with tenant_scope(tenant.id):
            assert ReceiptLine.objects.get(pk=linha.data["id"]).status == "needs_review"

    def test_apagar_uma_rececao_confirmada_a_meio_do_pedido_da_409_e_nao_500(self):
        """A mesma corrida no `DELETE`: o `apagar_rascunho` levanta a mesma coisa."""
        tenant, _, _, rececao = _loja_com_rececao_por_rever("corrida-apagar")
        api = _sessao("gerente-corrida-apagar@test.com")

        with mock.patch.object(
            views,
            "apagar_rascunho",
            _corrida_que_confirma(rececao.id, services.apagar_rascunho),
        ):
            recusa = api.delete(f"/api/v1/receipts/{rececao.id}")

        assert recusa.status_code == 409, recusa.data
        assert recusa.data["code"] == "rececao_confirmada"
        with tenant_scope(tenant.id):
            assert Receipt.objects.filter(pk=rececao.id).exists()
