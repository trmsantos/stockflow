"""O chat sobre stock, ponta a ponta e sem rede (ADR 0027).

O que este ficheiro mede, por secção:

1. **O contrato HTTP**: `POST` cria e responde 202, o `GET` da conversa é o alvo
   do polling, a lista é só das minhas, o `DELETE` é real; as recusas saem com
   `code` — 503 sem chave ou sem modelo, 429 nos dois tetos diários, 409
   `resposta_pendente` e `conversa_cheia`, 429 do throttle `assistente`.
2. **A conversa é da pessoa**: outro utilizador do mesmo tenant leva 404, outro
   tenant leva 404, e as duas tabelas estão sob RLS (o padrão do
   `tests/test_rls_isolation.py`).
3. **O ciclo de tool-use**: um cliente OpenAI **falso** injectado na fábrica
   `cliente()` devolve pedidos de tools e texto; mede-se o teto de iterações, a
   idempotência da tarefa, a língua no prompt, o papel a filtrar as tools, os
   erros do modelo a fechar o turno com código, e **"o chat nunca escreve no
   ledger"** — contagem de `StockMovement`, `StockLevel` e `Lot` igual antes e
   depois de uma conversa que chama as sete tools.
4. **A purga**: 90 dias, em lotes, tenant a tenant, e sem `system_scope` sobre o
   `accounts_tenant` — o guarda de âmbito do `conftest.py` levantaria.

Nenhum teste fala com a rede: o `openai` só entra pelo cliente falso.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import openai
import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts.middleware import SESSION_TENANT_KEY
from apps.accounts.models import Papel, Tenant, User
from apps.accounts.services import (
    BACKEND_DE_SESSAO,
    conceder_pertenca,
    criar_tenant,
    revogar_pertenca,
)
from apps.agents import tools
from apps.agents.models import (
    JANELA_DA_RESPOSTA,
    TURNOS_POR_CONVERSA,
    ChatMessage,
    CodigoDeErroDaMensagem,
    Conversation,
    EstadoDaMensagem,
)
from apps.agents.serializers import MensagemOutSerializer
from apps.agents.tasks import purgar_conversas, purgar_conversas_expiradas, responder_mensagem
from apps.catalog.models import Product, Supplier, UnidadeBase
from apps.inventory.models import Location, Lot, StockLevel, StockMovement
from apps.purchasing.models import Receipt, ReceiptLine
from apps.shared.db import tenant_scope
from config.celery import app

URL = "/api/v1/assistant/conversations"
CREDENCIAL = "farinha-fina-ao-amanhecer-9"
CHAVE_DE_TESTE = "chave-falsa-nunca-usada"


# ---------------------------------------------------------------------------
# O cliente falso: a forma da resposta do SDK, em objectos simples
# ---------------------------------------------------------------------------
def texto(conteudo: str, *, entrada: int = 100, saida: int = 20) -> SimpleNamespace:
    """Uma resposta do modelo só com texto (`finish_reason=stop`)."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=conteudo, tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=entrada, completion_tokens=saida),
    )


def pede_tools(*pedidos: tuple[str, dict[str, Any]]) -> SimpleNamespace:
    """Uma resposta do modelo a pedir uma ou mais tools."""
    chamadas = [
        SimpleNamespace(
            id=f"call_{i}",
            function=SimpleNamespace(name=nome, arguments=json.dumps(args, default=str)),
        )
        for i, (nome, args) in enumerate(pedidos, start=1)
    ]
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, tool_calls=chamadas),
                finish_reason="tool_calls",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=150, completion_tokens=30),
    )


@dataclass
class ClienteFalso:
    """O que a fábrica `cliente()` devolve nos testes: uma fila de respostas.

    Cada `create` regista os argumentos (para se poder afirmar que tools foram
    oferecidas e em que língua o sistema falou) e devolve a resposta seguinte da
    fila; com a fila vazia devolve texto, para um turno acabar sempre.
    """

    respostas: list[Any] = field(default_factory=list)
    chamadas: list[dict[str, Any]] = field(default_factory=list)
    erro: BaseException | None = None

    def __post_init__(self) -> None:
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> Any:
        self.chamadas.append(kwargs)
        if self.erro is not None:
            raise self.erro
        if self.respostas:
            return self.respostas.pop(0)
        return texto("Resposta por omissão.")

    @property
    def tools_oferecidas(self) -> list[list[str]]:
        return [
            [t["function"]["name"] for t in chamada["tools"]]
            if chamada.get("tools") not in (None, openai.NOT_GIVEN)
            else []
            for chamada in self.chamadas
        ]

    @property
    def sistemas(self) -> list[str]:
        return [chamada["messages"][0]["content"] for chamada in self.chamadas]


# ---------------------------------------------------------------------------
# Cenário
# ---------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True, slots=True)
class Cenario:
    alfa: Tenant
    beta: Tenant
    ana: User
    bruno: User
    carla: User
    farinha: Product
    loja: Location


@pytest.fixture(autouse=True)
def _cache_limpa() -> Iterator[None]:
    """O throttle conta em cache local ao processo."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def falso(monkeypatch: pytest.MonkeyPatch) -> ClienteFalso:
    """O cliente falso, injectado na fábrica, com o chat configurado."""
    cliente = ClienteFalso()
    monkeypatch.setattr("apps.agents.modelo.cliente", lambda: cliente)
    with override_settings(AGENTS_CHAT_API_KEY=CHAVE_DE_TESTE, AGENTS_CHAT_MODEL="gpt-5-mini"):
        yield cliente


@pytest.fixture
def cenario(transactional_db: None) -> Cenario:
    ana = User.objects.create_user("ana@alfa.pt", CREDENCIAL)
    bruno = User.objects.create_user("bruno@alfa.pt", CREDENCIAL)
    carla = User.objects.create_user("carla@beta.pt", CREDENCIAL)
    alfa = criar_tenant(name="Pastelaria Alfa")
    beta = criar_tenant(name="Café Beta")
    with tenant_scope(alfa.id):
        conceder_pertenca(user=ana, tenant_id=alfa.id, role=Papel.OWNER, display_name="Ana")
        conceder_pertenca(user=bruno, tenant_id=alfa.id, role=Papel.STAFF, display_name="Bruno")
        loja = Location.objects.create(tenant=alfa, name="Loja", position=1)
        farinha = Product.objects.create(
            tenant=alfa,
            short_name="Farinha T65",
            sku="FAR65",
            base_unit=UnidadeBase.GRAMA,
            display_unit="kg",
            display_factor=Decimal("1000"),
            min_quantity=Decimal("20000"),
            track_lots=True,
            expiry_kind="best_before",
        )
        lote = Lot.objects.create(
            tenant=alfa,
            product=farinha,
            code="L1",
            expires_at=timezone.now() + timedelta(days=3),
            received_at=timezone.now(),
        )
        StockLevel.objects.create(
            tenant=alfa,
            product=farinha,
            location=loja,
            lot=lote,
            quantity=Decimal("12500"),
            unit_cost=Decimal("0.0033"),
        )
        StockMovement.objects.create(
            tenant=alfa,
            product=farinha,
            location=loja,
            lot=lote,
            movement_type="receipt",
            quantity=Decimal("12500"),
            unit_cost=Decimal("0.0033"),
            occurred_at=timezone.now(),
            created_by=ana,
            created_by_name="Ana",
        )
        fornecedor = Supplier.objects.create(tenant=alfa, name="Moagem", nif="500000001")
        rececao = Receipt.objects.create(
            tenant=alfa,
            supplier=fornecedor,
            doc_type="FT",
            received_at=timezone.now(),
            location=loja,
            confirmed_at=timezone.now(),
        )
        ReceiptLine.objects.create(
            tenant=alfa,
            receipt=rececao,
            position=1,
            description="FARINHA",
            quantity_received=Decimal("25"),
            location=loja,
            kind="goods",
            status="confirmed",
            product=farinha,
            line_total=Decimal("41.20"),
        )
    with tenant_scope(beta.id):
        conceder_pertenca(user=carla, tenant_id=beta.id, role=Papel.OWNER, display_name="Carla")
    return Cenario(
        alfa=alfa, beta=beta, ana=ana, bruno=bruno, carla=carla, farinha=farinha, loja=loja
    )


def _cliente(user: User, tenant: Tenant, *, lingua: str = "pt-PT") -> Client:
    cliente = Client(headers={"accept-language": lingua})
    cliente.force_login(user, backend=BACKEND_DE_SESSAO)
    sessao = cliente.session
    sessao[SESSION_TENANT_KEY] = str(tenant.id)
    sessao.save()
    return cliente


def _perguntar(cliente: Client, pergunta: str = "Quanto tenho de farinha?") -> Any:
    return cliente.post(URL, data={"question": pergunta}, content_type="application/json")


def _mensagens(tenant_id: UUID, conversa_id: str) -> list[ChatMessage]:
    with tenant_scope(tenant_id):
        return list(ChatMessage.objects.filter(conversation_id=conversa_id).order_by("position"))


def _sem_tarefa(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Captura o `.delay()` em vez de correr a tarefa: deixa turnos `pendente`."""
    enfileiradas: list[dict[str, Any]] = []
    monkeypatch.setattr(responder_mensagem, "delay", lambda **kw: enfileiradas.append(kw))
    return enfileiradas


# ---------------------------------------------------------------------------
# 1. O contrato HTTP
# ---------------------------------------------------------------------------
def test_o_post_cria_a_conversa_responde_202_e_a_tarefa_responde(
    cenario: Cenario, falso: ClienteFalso
) -> None:
    """O caminho feliz inteiro: 202 com o turno `pendente`, e o `GET` já respondido.

    Com `CELERY_TASK_ALWAYS_EAGER` a tarefa corre no `on_commit` do `POST`, logo
    o `GET` seguinte lê o turno `respondida`, com o rasto da tool e os tokens.
    """
    falso.respostas = [
        pede_tools(("procurar_artigos", {"q": "farinha"})),
        texto("Tens 12,5 kg de Farinha T65 na Loja."),
    ]
    cliente = _cliente(cenario.ana, cenario.alfa)

    resposta = _perguntar(cliente)

    assert resposta.status_code == 202, resposta.content
    corpo = resposta.json()
    assert corpo["title"] == "Quanto tenho de farinha?"
    assert len(corpo["messages"]) == 1

    detalhe = cliente.get(f"{URL}/{corpo['id']}").json()
    turno = detalhe["messages"][0]
    assert turno["status"] == "respondida"
    assert turno["answer"] == "Tens 12,5 kg de Farinha T65 na Loja."
    assert turno["language"] == "pt-pt"
    assert turno["role_at_time"] == "owner"
    assert turno["asked_by_name"] == "Ana"
    assert turno["error_code"] is None
    assert turno["model"] == "gpt-5-mini"
    assert [t["name"] for t in turno["tool_calls"]] == ["procurar_artigos"]
    assert turno["tool_calls"][0] == {
        "name": "procurar_artigos",
        "args": {"q": "farinha", "limite": 10},
        "rows": 1,
        "truncated": False,
        "ok": True,
        "ms": turno["tool_calls"][0]["ms"],
    }
    assert turno["input_tokens"] == 250
    assert turno["output_tokens"] == 50
    assert Decimal(turno["cost_eur"]) > 0
    assert turno["started_at"] is not None and turno["finished_at"] is not None
    assert len(falso.chamadas) == 2
    # A pergunta vai como mensagem `user` e nunca no sistema; o resultado da
    # tool vai como mensagem `tool` com o id do pedido.
    segunda = falso.chamadas[1]["messages"]
    assert segunda[0]["role"] == "system"
    assert "Quanto tenho de farinha?" not in segunda[0]["content"]
    assert segunda[1] == {"role": "user", "content": "Quanto tenho de farinha?"}
    assert segunda[2]["role"] == "assistant" and segunda[2]["tool_calls"][0]["id"] == "call_1"
    assert segunda[3]["role"] == "tool" and segunda[3]["tool_call_id"] == "call_1"
    assert "Farinha T65" in segunda[3]["content"]
    assert falso.chamadas[0]["max_completion_tokens"] == settings.AGENTS_CHAT_MAX_TOKENS


def test_a_pergunta_seguinte_leva_o_historico_e_e_202(
    cenario: Cenario, falso: ClienteFalso
) -> None:
    falso.respostas = [texto("Primeira."), texto("Segunda.")]
    cliente = _cliente(cenario.ana, cenario.alfa)
    conversa_id = _perguntar(cliente).json()["id"]

    resposta = cliente.post(
        f"{URL}/{conversa_id}/messages",
        data={"question": "E de açúcar?"},
        content_type="application/json",
    )

    assert resposta.status_code == 202, resposta.content
    assert resposta.json()["position"] == 2
    turnos = _mensagens(cenario.alfa.id, conversa_id)
    assert [t.status for t in turnos] == ["respondida", "respondida"]
    historico = falso.chamadas[1]["messages"]
    assert [m["role"] for m in historico] == ["system", "user", "assistant", "user"]
    assert historico[2]["content"] == "Primeira."


def test_sem_chave_o_post_e_503_antes_de_criar_linha(cenario: Cenario) -> None:
    cliente = _cliente(cenario.ana, cenario.alfa)
    with override_settings(AGENTS_CHAT_API_KEY=""):
        resposta = _perguntar(cliente)

    assert resposta.status_code == 503
    assert resposta.json()["code"] == "assistente_indisponivel"
    assert "configurado" in resposta.json()["detail"]
    with tenant_scope(cenario.alfa.id):
        assert Conversation.objects.count() == 0


def test_sem_modelo_o_post_e_503(cenario: Cenario) -> None:
    cliente = _cliente(cenario.ana, cenario.alfa)
    with override_settings(AGENTS_CHAT_API_KEY=CHAVE_DE_TESTE, AGENTS_CHAT_MODEL=""):
        resposta = _perguntar(cliente)

    assert resposta.status_code == 503
    assert resposta.json()["code"] == "assistente_indisponivel"


def test_o_teto_diario_de_perguntas_por_pessoa_e_429(
    cenario: Cenario, falso: ClienteFalso
) -> None:
    cliente = _cliente(cenario.ana, cenario.alfa)
    with override_settings(AGENTS_CHAT_DAILY_MESSAGES_PER_USER=1):
        assert _perguntar(cliente).status_code == 202
        resposta = _perguntar(cliente)

    assert resposta.status_code == 429
    assert resposta.json()["code"] == "teto_diario_atingido"
    # Outra pessoa do mesmo estabelecimento tem o seu próprio contador.
    with override_settings(AGENTS_CHAT_DAILY_MESSAGES_PER_USER=1):
        assert _perguntar(_cliente(cenario.bruno, cenario.alfa)).status_code == 202


def test_o_orcamento_diario_do_tenant_e_429_no_post_e_teto_de_custo_na_tarefa(
    cenario: Cenario, falso: ClienteFalso
) -> None:
    """Os euros gastos hoje travam o `POST`; e a tarefa trava a meio de um turno."""
    cliente = _cliente(cenario.ana, cenario.alfa)
    falso.respostas = [
        pede_tools(("procurar_artigos", {"q": "farinha"})),
        texto("nunca chega aqui"),
    ]
    with override_settings(AGENTS_CHAT_DAILY_BUDGET_EUR=Decimal("0.000010")):
        conversa_id = _perguntar(cliente).json()["id"]
        turno = _mensagens(cenario.alfa.id, conversa_id)[0]
        assert turno.status == EstadoDaMensagem.ERRO
        assert turno.error_code == CodigoDeErroDaMensagem.TETO_DE_CUSTO
        assert turno.iterations == 1, "a primeira chamada pagou-se; a segunda foi recusada"
        assert len(falso.chamadas) == 1
        # E o dia está esgotado para o estabelecimento inteiro.
        resposta = _perguntar(_cliente(cenario.bruno, cenario.alfa))

    assert resposta.status_code == 429
    assert resposta.json()["code"] == "teto_diario_atingido"


def test_um_turno_em_curso_e_409_resposta_pendente(
    cenario: Cenario, falso: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sem_tarefa(monkeypatch)
    cliente = _cliente(cenario.ana, cenario.alfa)
    conversa_id = _perguntar(cliente).json()["id"]

    resposta = cliente.post(
        f"{URL}/{conversa_id}/messages",
        data={"question": "outra"},
        content_type="application/json",
    )

    assert resposta.status_code == 409
    assert resposta.json()["code"] == "resposta_pendente"
    assert "a responder" in resposta.json()["detail"]


def test_um_turno_parado_le_se_tempo_esgotado_e_nao_bloqueia(
    cenario: Cenario, falso: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`tempo_esgotado` por derivação, nunca por escrita — e a conversa segue."""
    _sem_tarefa(monkeypatch)
    cliente = _cliente(cenario.ana, cenario.alfa)
    conversa_id = _perguntar(cliente).json()["id"]
    with tenant_scope(cenario.alfa.id):
        ChatMessage.objects.filter(conversation_id=conversa_id).update(
            created_at=timezone.now() - JANELA_DA_RESPOSTA - timedelta(seconds=1)
        )

    turno = cliente.get(f"{URL}/{conversa_id}").json()["messages"][0]
    assert turno["status"] == "erro"
    assert turno["error_code"] == "tempo_esgotado"
    with tenant_scope(cenario.alfa.id):
        guardado = ChatMessage.objects.get(conversation_id=conversa_id)
        assert guardado.status == EstadoDaMensagem.PENDENTE, "derivado, nunca escrito"

    seguinte = cliente.post(
        f"{URL}/{conversa_id}/messages",
        data={"question": "outra"},
        content_type="application/json",
    )
    assert seguinte.status_code == 202


def test_a_conversa_cheia_e_409(
    cenario: Cenario, falso: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    cliente = _cliente(cenario.ana, cenario.alfa)
    conversa_id = _perguntar(cliente).json()["id"]
    with tenant_scope(cenario.alfa.id):
        conversa = Conversation.objects.get(pk=conversa_id)
        for posicao in range(2, TURNOS_POR_CONVERSA + 1):
            ChatMessage.objects.create(
                tenant=cenario.alfa,
                conversation=conversa,
                position=posicao,
                asked_by=cenario.ana,
                role_at_time="owner",
                question="?",
                language="pt-pt",
                status=EstadoDaMensagem.RESPONDIDA,
                idempotency_key=f"chat:{uuid4()}",
            )

    # Sem o teto por pessoa à frente: os tetos diários verificam-se primeiro, e
    # os 29 turnos semeados contam como perguntas de hoje da Ana.
    with override_settings(AGENTS_CHAT_DAILY_MESSAGES_PER_USER=100):
        resposta = cliente.post(
            f"{URL}/{conversa_id}/messages",
            data={"question": "a trigésima primeira"},
            content_type="application/json",
        )

    assert resposta.status_code == 409
    assert resposta.json()["code"] == "conversa_cheia"


def test_o_throttle_assistente_e_10_por_minuto_nas_escritas(
    cenario: Cenario, falso: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sem_tarefa(monkeypatch)
    cliente = _cliente(cenario.ana, cenario.alfa)
    with override_settings(AGENTS_CHAT_DAILY_MESSAGES_PER_USER=100):
        codigos = [_perguntar(cliente).status_code for _ in range(11)]

    assert codigos[:10] == [202] * 10
    assert codigos[10] == 429
    # As leituras não contam no balde: a lista continua a responder.
    assert cliente.get(URL).status_code == 200


def test_uma_pergunta_vazia_ou_demasiado_longa_e_400(cenario: Cenario, falso: ClienteFalso) -> None:
    cliente = _cliente(cenario.ana, cenario.alfa)
    assert _perguntar(cliente, "   ").status_code == 400
    assert _perguntar(cliente, "x" * 2001).status_code == 400
    assert cliente.post(URL, data={}, content_type="application/json").status_code == 400


def test_a_lista_e_so_das_minhas_e_o_delete_e_real(
    cenario: Cenario, falso: ClienteFalso
) -> None:
    ana = _cliente(cenario.ana, cenario.alfa)
    bruno = _cliente(cenario.bruno, cenario.alfa)
    minha = _perguntar(ana, "primeira").json()["id"]
    _perguntar(ana, "segunda")
    _perguntar(bruno, "do bruno")

    lista = ana.get(URL).json()
    assert lista["count"] == 2
    assert {c["title"] for c in lista["results"]} == {"primeira", "segunda"}
    assert "messages" not in lista["results"][0]

    assert ana.delete(f"{URL}/{minha}").status_code == 204
    assert ana.get(f"{URL}/{minha}").status_code == 404
    with tenant_scope(cenario.alfa.id):
        assert not ChatMessage.objects.filter(conversation_id=minha).exists(), "CASCADE"
        assert Conversation.objects.count() == 2


# ---------------------------------------------------------------------------
# 2. A conversa é da pessoa, e as tabelas estão sob RLS
# ---------------------------------------------------------------------------
def test_a_conversa_de_outro_utilizador_do_mesmo_tenant_e_404(
    cenario: Cenario, falso: ClienteFalso
) -> None:
    conversa_id = _perguntar(_cliente(cenario.ana, cenario.alfa)).json()["id"]
    bruno = _cliente(cenario.bruno, cenario.alfa)

    assert bruno.get(f"{URL}/{conversa_id}").status_code == 404
    assert (
        bruno.post(
            f"{URL}/{conversa_id}/messages",
            data={"question": "?"},
            content_type="application/json",
        ).status_code
        == 404
    )
    assert bruno.delete(f"{URL}/{conversa_id}").status_code == 404
    assert bruno.get(URL).json()["count"] == 0


def test_a_conversa_de_outro_tenant_e_404(cenario: Cenario, falso: ClienteFalso) -> None:
    conversa_id = _perguntar(_cliente(cenario.ana, cenario.alfa)).json()["id"]
    carla = _cliente(cenario.carla, cenario.beta)

    assert carla.get(f"{URL}/{conversa_id}").status_code == 404
    assert carla.delete(f"{URL}/{conversa_id}").status_code == 404
    assert carla.get(URL).json()["count"] == 0


@pytest.mark.sem_ambito_de_rls
def test_as_duas_tabelas_estao_sob_rls(cenario: Cenario, falso: ClienteFalso) -> None:
    """Fora de âmbito, zero linhas sem erro; no âmbito de outro tenant, zero."""
    conversa_id = _perguntar(_cliente(cenario.ana, cenario.alfa)).json()["id"]

    assert Conversation.objects.count() == 0
    assert ChatMessage.objects.count() == 0
    with tenant_scope(cenario.beta.id):
        assert Conversation.objects.filter(pk=conversa_id).count() == 0
        assert ChatMessage.objects.count() == 0
    with tenant_scope(cenario.alfa.id):
        assert Conversation.objects.filter(pk=conversa_id).count() == 1
        assert ChatMessage.objects.count() == 1


# ---------------------------------------------------------------------------
# 3. O ciclo de tool-use
# ---------------------------------------------------------------------------
def test_o_chat_nunca_escreve_no_ledger(cenario: Cenario, falso: ClienteFalso) -> None:
    """Uma conversa que chama as sete tools deixa o ledger como o encontrou."""
    hoje = timezone.localdate()
    falso.respostas = [
        pede_tools(
            ("procurar_artigos", {"q": "farinha"}),
            ("procurar_fornecedores", {"q": "moagem"}),
            ("saldo_de_artigo", {"product_id": str(cenario.farinha.id)}),
        ),
        pede_tools(
            ("artigos_abaixo_do_minimo", {}),
            ("lotes_a_vencer", {"dias": 7}),
            ("movimentos_de_artigo", {"product_id": str(cenario.farinha.id)}),
            (
                "compras_por_periodo",
                {"desde": str(hoje - timedelta(days=30)), "ate": str(hoje)},
            ),
        ),
        texto("Está tudo aqui."),
    ]
    with tenant_scope(cenario.alfa.id):
        antes = (StockMovement.objects.count(), StockLevel.objects.count(), Lot.objects.count())
        saldo_antes = StockLevel.objects.get(product=cenario.farinha).quantity

    conversa_id = _perguntar(_cliente(cenario.ana, cenario.alfa)).json()["id"]

    turno = _mensagens(cenario.alfa.id, conversa_id)[0]
    assert turno.status == EstadoDaMensagem.RESPONDIDA
    assert [t["name"] for t in turno.chamadas_validadas] == list(tools.nomes_das_tools())
    assert all(t["ok"] for t in turno.chamadas_validadas), turno.tool_calls
    with tenant_scope(cenario.alfa.id):
        depois = (StockMovement.objects.count(), StockLevel.objects.count(), Lot.objects.count())
        assert depois == antes
        assert StockLevel.objects.get(product=cenario.farinha).quantity == saldo_antes


def test_o_teto_de_iteracoes_fecha_o_turno_com_erro(
    cenario: Cenario, falso: ClienteFalso
) -> None:
    """Um modelo que só pede tools pára ao sexto pedido — e a conta está gravada."""
    falso.respostas = [pede_tools(("procurar_artigos", {"q": "farinha"})) for _ in range(10)]

    conversa_id = _perguntar(_cliente(cenario.ana, cenario.alfa)).json()["id"]

    turno = _mensagens(cenario.alfa.id, conversa_id)[0]
    assert turno.status == EstadoDaMensagem.ERRO
    assert turno.error_code == CodigoDeErroDaMensagem.TETO_DE_ITERACOES
    assert turno.iterations == settings.AGENTS_CHAT_MAX_TOOL_ITERATIONS == 6
    assert len(falso.chamadas) == 6
    assert len(turno.chamadas_validadas) == 6
    assert turno.input_tokens == 6 * 150
    assert "\n  File " not in turno.error


def test_a_tarefa_e_idempotente_pela_linha(
    cenario: Cenario, falso: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    enfileiradas = _sem_tarefa(monkeypatch)
    _perguntar(_cliente(cenario.ana, cenario.alfa))
    argumentos = enfileiradas[0]
    assert argumentos["tenant_id"] == str(cenario.alfa.id)

    assert responder_mensagem(**argumentos) == "respondida"
    assert responder_mensagem(**argumentos) == "ja_tratada"
    assert len(falso.chamadas) == 1, "uma segunda entrega não paga duas vezes"


def test_a_lingua_do_pedido_vai_no_prompt(cenario: Cenario, falso: ClienteFalso) -> None:
    conversa_id = _perguntar(_cliente(cenario.ana, cenario.alfa, lingua="en-US,en;q=0.9")).json()[
        "id"
    ]

    turno = _mensagens(cenario.alfa.id, conversa_id)[0]
    assert turno.language == "en"
    assert "Always answer in English." in falso.sistemas[0]
    assert "Pastelaria Alfa" in falso.sistemas[0]
    assert "Loja" in falso.sistemas[0]

    _perguntar(_cliente(cenario.ana, cenario.alfa, lingua="pt-BR,pt;q=0.9"))
    assert "português de Portugal" in falso.sistemas[1]


def test_o_staff_nao_recebe_compras_por_periodo_e_a_recusa_e_dupla(
    cenario: Cenario, falso: ClienteFalso
) -> None:
    """A lista oferecida é filtrada pelo papel, e o despachante recusa outra vez."""
    hoje = timezone.localdate()
    falso.respostas = [
        pede_tools(("compras_por_periodo", {"desde": str(hoje), "ate": str(hoje)})),
        texto("Não posso."),
    ]

    conversa_id = _perguntar(_cliente(cenario.bruno, cenario.alfa)).json()["id"]

    assert "compras_por_periodo" not in falso.tools_oferecidas[0]
    assert set(falso.tools_oferecidas[0]) == set(tools.nomes_das_tools()) - {
        "compras_por_periodo"
    }
    turno = _mensagens(cenario.alfa.id, conversa_id)[0]
    assert turno.role_at_time == "staff"
    rasto = turno.chamadas_validadas
    assert rasto[0]["name"] == "compras_por_periodo" and rasto[0]["ok"] is False
    assert "tool_nao_disponivel" in falso.chamadas[1]["messages"][3]["content"]

    # O dono recebe as sete.
    _perguntar(_cliente(cenario.ana, cenario.alfa))
    assert falso.tools_oferecidas[-1] == list(tools.nomes_das_tools())


class _TimeoutDoFornecedor(openai.APITimeoutError):
    """Um `APITimeoutError` sem o `httpx.Request` que o construtor real exige.

    O que o `conversar` faz com a excepção é `isinstance` e `type(exc).__name__`;
    construir a de verdade obrigava a importar o cliente HTTP do SDK só para
    fabricar um pedido que ninguém envia.
    """

    def __init__(self) -> None:
        Exception.__init__(self, "Request timed out.")


class _LimiteDoFornecedor(openai.RateLimitError):
    def __init__(self) -> None:
        Exception.__init__(self, "rate limited: corpo com a pergunta")


@pytest.mark.parametrize(
    ("erro", "codigo"),
    [
        (_TimeoutDoFornecedor(), CodigoDeErroDaMensagem.TEMPO_ESGOTADO),
        (_LimiteDoFornecedor(), CodigoDeErroDaMensagem.ERRO_DO_MODELO),
    ],
)
def test_um_erro_do_fornecedor_fecha_o_turno_com_codigo(
    cenario: Cenario, falso: ClienteFalso, erro: BaseException, codigo: str
) -> None:
    falso.erro = erro

    conversa_id = _perguntar(_cliente(cenario.ana, cenario.alfa)).json()["id"]

    turno = _mensagens(cenario.alfa.id, conversa_id)[0]
    assert turno.status == EstadoDaMensagem.ERRO
    assert turno.error_code == codigo
    assert "Traceback" not in turno.error and "pergunta" not in turno.error


def test_uma_resposta_sem_texto_e_resposta_invalida(
    cenario: Cenario, falso: ClienteFalso
) -> None:
    falso.respostas = [texto("")]
    conversa_id = _perguntar(_cliente(cenario.ana, cenario.alfa)).json()["id"]

    turno = _mensagens(cenario.alfa.id, conversa_id)[0]
    assert turno.error_code == CodigoDeErroDaMensagem.RESPOSTA_INVALIDA


def test_a_pertenca_revogada_fecha_o_turno_sem_chamar_o_modelo(
    cenario: Cenario, falso: ClienteFalso, monkeypatch: pytest.MonkeyPatch
) -> None:
    enfileiradas = _sem_tarefa(monkeypatch)
    _perguntar(_cliente(cenario.bruno, cenario.alfa))
    with tenant_scope(cenario.alfa.id):
        revogar_pertenca(user=cenario.bruno, tenant_id=cenario.alfa.id)

    assert responder_mensagem(**enfileiradas[0]) == "erro"

    with tenant_scope(cenario.alfa.id):
        turno = ChatMessage.objects.get()
    assert turno.error_code == CodigoDeErroDaMensagem.PERTENCA_REVOGADA
    assert falso.chamadas == []


def test_o_tool_calls_e_revalidado_a_leitura(cenario: Cenario, falso: ClienteFalso) -> None:
    conversa_id = _perguntar(_cliente(cenario.ana, cenario.alfa)).json()["id"]
    with tenant_scope(cenario.alfa.id):
        turno = ChatMessage.objects.get(conversation_id=conversa_id)
        turno.tool_calls = [
            {"name": "procurar_artigos", "args": {"q": "x"}, "rows": 1, "truncated": False, "ok": True, "ms": 3},
            {"name": "", "args": {}, "rows": 0, "truncated": False, "ok": True, "ms": 0},
            {"name": "sem_forma", "args": "nao-e-dict", "rows": "1"},
            "lixo",
            {"name": "bool_no_rows", "args": {}, "rows": True, "truncated": False, "ok": True, "ms": 0},
        ]
        turno.save(update_fields=["tool_calls"])
        dados = MensagemOutSerializer(turno).data

    assert [t["name"] for t in dados["tool_calls"]] == ["procurar_artigos"]


def test_o_registo_de_tools_e_fechado_e_so_de_leitura() -> None:
    """As sete da ADR, por nome; e nenhum ficheiro do `agents` importa escrita do ledger."""
    assert tools.nomes_das_tools() == (
        "procurar_artigos",
        "procurar_fornecedores",
        "saldo_de_artigo",
        "artigos_abaixo_do_minimo",
        "lotes_a_vencer",
        "movimentos_de_artigo",
        "compras_por_periodo",
    )
    assert tools.REGISTO["compras_por_periodo"].papeis == frozenset({"owner", "manager"})
    for nome in tools.nomes_das_tools():
        if nome != "compras_por_periodo":
            assert tools.REGISTO[nome].papeis == frozenset({"owner", "manager", "staff"})

    nomes_de_escrita = (
        "record_movements",
        "get_or_create_lots",
        "criar_localizacao",
        "criar_produto",
        "criar_fornecedor",
        "criar_embalagem",
        "memorizar_correspondencias",
        "criar_documento",
        "criar_receçao",
        "adicionar_linha_recepção",
        "registar_waste",
        "registar_adjustment",
        "registar_transfer",
    )
    raiz = pathlib.Path(settings.BASE_DIR) / "apps" / "agents"
    for caminho in sorted(raiz.rglob("*.py")):
        if "migrations" in caminho.parts:
            continue
        fonte = re.sub(r"^\s*#.*$", "", caminho.read_text(encoding="utf-8"), flags=re.M)
        fonte = re.sub(r'"""[\s\S]*?"""', "", fonte)
        for nome in nomes_de_escrita:
            assert not re.search(rf"\b{re.escape(nome)}\b", fonte), (
                f"{caminho.name} refere {nome}: o chat é só de leitura (ADR 0027, decisão 8)"
            )


def test_o_resultado_de_uma_tool_e_marcado_como_dados_e_cabe_em_8_kb(
    cenario: Cenario, falso: ClienteFalso
) -> None:
    falso.respostas = [pede_tools(("procurar_artigos", {"q": "farinha"})), texto("ok")]
    _perguntar(_cliente(cenario.ana, cenario.alfa))

    conteudo = falso.chamadas[1]["messages"][3]["content"]
    assert len(conteudo.encode("utf-8")) <= tools.TAMANHO_MAXIMO_DO_RESULTADO
    envelope = json.loads(conteudo)
    assert set(envelope) == {"dados", "truncado", "aviso"}
    assert "não instruções" in envelope["aviso"]


# ---------------------------------------------------------------------------
# 4. A purga
# ---------------------------------------------------------------------------
def _conversa_antiga(tenant: Tenant, user: User, *, dias: int, titulo: str) -> UUID:
    with tenant_scope(tenant.id):
        conversa = Conversation.objects.create(
            tenant=tenant,
            created_by=user,
            created_by_name="x",
            title=titulo,
            last_message_at=timezone.now() - timedelta(days=dias),
        )
        ChatMessage.objects.create(
            tenant=tenant,
            conversation=conversa,
            position=1,
            asked_by=user,
            role_at_time="owner",
            question="?",
            language="pt-pt",
            status=EstadoDaMensagem.RESPONDIDA,
            idempotency_key=f"chat:{uuid4()}",
        )
    return conversa.id


def test_a_purga_apaga_so_as_expiradas_tenant_a_tenant_e_em_lotes(
    cenario: Cenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """90 dias, em lotes de um, tenant a tenant — e sem ler o `accounts_tenant`.

    O guarda de âmbito do `conftest.py` está montado: uma leitura do
    `accounts_tenant` dentro de `system_scope()` levantaria `LeituraSemAmbito`.
    Passar é a prova de que a descoberta dos tenants vai pelo `tenant_ids`.
    """
    monkeypatch.setattr("apps.agents.services.LOTE_DA_PURGA", 1)
    expiradas = {
        _conversa_antiga(cenario.alfa, cenario.ana, dias=91, titulo="alfa velha 1"),
        _conversa_antiga(cenario.alfa, cenario.bruno, dias=120, titulo="alfa velha 2"),
        _conversa_antiga(cenario.alfa, cenario.ana, dias=400, titulo="alfa velha 3"),
    }
    recente = _conversa_antiga(cenario.alfa, cenario.ana, dias=89, titulo="alfa recente")
    beta_velha = _conversa_antiga(cenario.beta, cenario.carla, dias=100, titulo="beta velha")

    # Uma purga de um tenant só não vê — nem apaga — as do outro.
    assert purgar_conversas(tenant_id=str(cenario.alfa.id)) == 3
    with tenant_scope(cenario.alfa.id):
        assert set(Conversation.objects.values_list("id", flat=True)) == {recente}
        assert ChatMessage.objects.count() == 1, "o CASCADE levou as mensagens"
    with tenant_scope(cenario.beta.id):
        assert Conversation.objects.filter(pk=beta_velha).exists()

    # O cron descobre os tenants pelo `tenant_ids` e enfileira uma purga por cada.
    resultado = purgar_conversas_expiradas()

    assert resultado["tenants"] == 2
    with tenant_scope(cenario.beta.id):
        assert not Conversation.objects.filter(pk=beta_velha).exists()
    with tenant_scope(cenario.alfa.id):
        assert Conversation.objects.filter(pk=recente).exists()
        assert not Conversation.objects.filter(pk__in=expiradas).exists()


def test_o_cron_da_purga_e_uma_system_task_e_a_filha_e_uma_tenant_task() -> None:
    assert purgar_conversas_expiradas.tenant_scope_exempt is True
    assert purgar_conversas.tenant_scope_exempt is False
    assert responder_mensagem.tenant_scope_exempt is False


def test_o_beat_agenda_a_purga_uma_vez_por_dia() -> None:
    entrada = app.conf.beat_schedule["purgar-conversas-expiradas"]

    assert entrada["task"] == purgar_conversas_expiradas.name == "agents.purgar_conversas_expiradas"
    assert entrada["schedule"].hour == {4}
    assert entrada["options"]["expires"] == 3600


# ---------------------------------------------------------------------------
# Fornecedor OpenAI-compatível por `AGENTS_CHAT_BASE_URL`
# ---------------------------------------------------------------------------
def test_sem_url_base_o_cliente_vai_para_a_openai_com_max_completion_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import openai

    from apps.agents import modelo

    recebido: dict[str, object] = {}
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: recebido.update(kwargs) or object())
    with override_settings(AGENTS_CHAT_API_KEY="chave-de-teste", AGENTS_CHAT_BASE_URL=""):
        modelo.cliente()
        assert recebido["base_url"] is None
        assert modelo._limite_de_tokens(7) == {"max_completion_tokens": 7}


def test_com_url_base_o_cliente_vai_para_o_fornecedor_com_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import openai

    from apps.agents import modelo

    recebido: dict[str, object] = {}
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: recebido.update(kwargs) or object())
    url = "https://exemplo.test/v1"
    with override_settings(AGENTS_CHAT_API_KEY="chave-de-teste", AGENTS_CHAT_BASE_URL=url):
        modelo.cliente()
        assert recebido["base_url"] == url
        assert recebido["api_key"] == "chave-de-teste"
        assert modelo._limite_de_tokens(7) == {"max_tokens": 7}
