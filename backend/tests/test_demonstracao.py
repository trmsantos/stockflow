"""O estabelecimento de demonstração (ADR 0018).

Cinco propriedades, e as três primeiras são as que custam dinheiro ou confiança
se falharem.

**1. A revogação nunca alcança um estabelecimento a sério.** Reinicializar o demo
revoga a pertença aos demos anteriores **desta pessoa** — e se o filtro `is_demo`
falhasse, o que este caminho fazia era retirar a alguém o acesso ao seu próprio
negócio. É a asserção mais importante do ficheiro
(`test_reinicializar_nao_toca_no_estabelecimento_a_serio`), e está feita com uma
conta que tem os dois.

**2. O demo não cria contas** (ADR 0018, decisão 6). O registo self-service não
existe no v1 (ADR 0010) e um semeador que criasse a conta reabria-o por uma porta
de serviço. Um email desconhecido é um erro do operador.

**3. `demonstracao` viaja no `SessaoOut`, nos dois sítios.** É a única diferença
visível de um demo e é o que alimenta a faixa permanente e o item marcado no
seletor — se não viajar no `tenant_ativo` **e** em cada entrada de `tenants`, o
cromado não tem com que se ligar.

**4. Um demo por pessoa.** Correr duas vezes dá dois uuids e uma pertença: o
anterior fica inalcançável (a query do `TenantMiddleware` devolve zero linhas e a
resposta é 403), mas as linhas ficam lá — o caminho normal nunca apaga nada,
porque o `inventory_stockmovement` nascerá com `REVOKE UPDATE, DELETE` ao role da
app.

**5. O demo comporta-se como um estabelecimento normal.** Entra-se nele, o menu
vem igual, e a configuração muda lá — menos o nome (ADR 0018 pela mão da sessão 0;
medido em `tests/test_estabelecimento.py`). É a decisão 1 inteira: "nenhum
endpoint sabe que ele existe".

## Porque é que todos levam `transactional_db`

A razão dos outros ficheiros: com a transação do pytest-django por fora, o
`set_config('app.tenant_id', ..., true)` que o `tenant_scope` corre só reverte no
fim **dela** e não no fim do bloco `with`. Este ficheiro abre e fecha vários
âmbitos por teste — o `_revogar_demonstracoes_anteriores` abre um por candidato —,
pelo que sem isto as asserções mediriam um âmbito ainda aberto.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client

from apps.accounts.api import semear_demonstracao
from apps.accounts.middleware import SESSION_TENANT_KEY
from apps.accounts.models import Papel, Tenant, User
from apps.accounts.services import (
    BACKEND_DE_SESSAO,
    conceder_pertenca,
    criar_tenant,
)
from apps.shared.db import tenant_scope

URL_SESSAO = "/api/v1/auth/sessao"


@pytest.fixture(autouse=True)
def _cache_limpa() -> Iterator[None]:
    """O throttle do DRF conta em cache, e a cache é local ao processo."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def ana(transactional_db: None) -> User:
    """Uma conta sem estabelecimento nenhum: o caso de quem vai experimentar."""
    return User.objects.create_user("ana@experimenta.pt")


def _e_demo(tenant_id: UUID) -> bool:
    """Lido **dentro do âmbito**: o `accounts_tenant` tem política sobre `id`."""
    with tenant_scope(tenant_id):
        return Tenant.objects.values_list("is_demo", flat=True).get()


def _semear(email: str = "ana@experimenta.pt", **kwargs: Any) -> Any:
    return semear_demonstracao(
        email=email,
        nome=kwargs.pop("nome", "Pastelaria de Demonstração"),
        display_name=kwargs.pop("display_name", "A experimentar"),
    )


def _cliente(user: User, tenant_id: UUID | None = None) -> Client:
    cliente = Client()
    cliente.force_login(user, backend=BACKEND_DE_SESSAO)
    if tenant_id is not None:
        sessao = cliente.session
        sessao[SESSION_TENANT_KEY] = str(tenant_id)
        sessao.save()
    return cliente


# ---------------------------------------------------------------------------
# 1. O caminho feliz
# ---------------------------------------------------------------------------


def test_semear_cria_o_estabelecimento_com_a_bandeira_e_a_pertenca(ana: User) -> None:
    """Um estabelecimento `is_demo`, com a pessoa como `owner` dele."""
    resultado = _semear()

    assert resultado.user.pk == ana.pk
    assert resultado.revogados == ()
    assert _e_demo(resultado.tenant.id) is True

    ana.refresh_from_db(fields=["tenant_ids"])
    assert ana.tenant_ids == [resultado.tenant.id]


def test_o_demo_e_so_de_quem_o_pediu(ana: User) -> None:
    """Decisão 6: quem o vê é quem tiver um `Membership` nele, e mais ninguém.

    Não há nada de novo a testar no isolamento — é a mesma política de qualquer
    outro cliente, na mesma ligação sem `BYPASSRLS`. O que se afirma aqui é que o
    semeador não concede pertença a mais ninguém: um demo "para a equipa" seria
    mutável por todos, e a primeira pessoa que lá registasse uma quebra mudava o
    que a próxima encontra.
    """
    outra = User.objects.create_user("bruno@outra.pt")
    resultado = _semear()

    outra.refresh_from_db(fields=["tenant_ids"])
    assert outra.tenant_ids == []
    assert _cliente(outra, resultado.tenant.id).get(URL_SESSAO).json()["tenant_ativo"] is None


# ---------------------------------------------------------------------------
# 2. Não cria contas
# ---------------------------------------------------------------------------


def test_um_email_sem_conta_e_recusado_e_nao_cria_nada(transactional_db: None) -> None:
    """Decisão 6, e é a asserção que fecha a porta de serviço.

    O registo self-service não existe no v1 (ADR 0010) e três perguntas ficaram
    em aberto por causa dele. Um semeador que criasse a conta reabria-o sem ADR —
    e, pior, criava-a sem password utilizável e sem caminho de activação.
    """
    with pytest.raises(ValidationError) as erro:
        _semear(email="ninguem@parte-nenhuma.pt")

    assert "email" in erro.value.message_dict
    assert not User.objects.filter(email="ninguem@parte-nenhuma.pt").exists()

    # **"Nenhum estabelecimento foi criado" não é observável, e isso é a
    # propriedade e não uma falha deste teste.** Escrevi-o à primeira com um
    # `Tenant.objects.count()` antes e depois, e o guarda do `conftest.py`
    # recusou as duas leituras — com razão nas duas: o `accounts_tenant` tem
    # política sobre `id` e a política **não** reconhece o âmbito de sistema
    # (ao contrário das tabelas da ADR 0005), logo nem o `system_scope()`
    # consegue contar tenants. Uma contagem fora de âmbito devolveria zero pela
    # política e o teste passava por não ver nada — o pior modo de passar que
    # existe.
    #
    # O que fica afirmado é o que o role da app **pode** saber: a conta não
    # nasceu. E isso basta para a propriedade que importa, porque um
    # estabelecimento sem pertença é inalcançável por definição (ADR 0007: a
    # sessão escolhe o âmbito a partir do `tenant_ids`) — não há caminho por onde
    # alguém chegue a ele.


# ---------------------------------------------------------------------------
# 3. Reinicializar: cria outro e revoga o anterior — e **só** demos
# ---------------------------------------------------------------------------


def test_reinicializar_cria_outro_e_revoga_o_anterior(ana: User) -> None:
    """Dois uuids, uma pertença, e nada apagado.

    O caminho normal nunca apaga: o `inventory_stockmovement` nascerá com
    `REVOKE UPDATE, DELETE` ao role da app (`SECURITY.md` §3), logo a app não
    consegue limpar um ledger — e é bom que não consiga. O que muda é a
    alcançabilidade, não a existência: as duas linhas continuam na tabela.
    """
    primeiro = _semear().tenant.id
    segundo_resultado = _semear()
    segundo = segundo_resultado.tenant.id

    assert primeiro != segundo
    assert segundo_resultado.revogados == (primeiro,)

    ana.refresh_from_db(fields=["tenant_ids"])
    assert ana.tenant_ids == [segundo], "o seletor passa a ter um demo só"

    # E o anterior **continua a existir**: não foi apagado, ficou inalcançável.
    # Lido dentro do âmbito **dele**, que é a única forma: a política compara
    # `id` com o GUC. Uma leitura sem âmbito devolvia zero linhas e este `assert`
    # falharia a dizer que a linha foi apagada quando não foi — o guarda do
    # `conftest.py` apanhou exactamente isso quando escrevi este teste à primeira.
    with tenant_scope(primeiro):
        assert Tenant.objects.filter(pk=primeiro).exists()


def test_o_demo_anterior_responde_403_e_nao_404(ana: User) -> None:
    """A forma da inalcançabilidade, medida pelo HTTP.

    É a propriedade que a decisão 5 descreve: "a partir desse momento ele é
    inalcançável por quem quer que seja, porque a query do `TenantMiddleware`
    devolve zero linhas e a resposta é 403". Sem pertença não há âmbito, e sem
    âmbito não há resposta nenhuma sobre aquele estabelecimento — nem a de que ele
    existe.
    """
    primeiro = _semear().tenant.id
    _semear()

    sessao = _cliente(ana, primeiro).get(URL_SESSAO).json()

    assert sessao["tenant_ativo"] is None, (
        "a sessão com o uuid do demo revogado não o confirma: o `tenant_ids` já "
        "não o tem e a política não devolveria linha nenhuma"
    )


def test_reinicializar_nao_toca_no_estabelecimento_a_serio(ana: User) -> None:
    """**A asserção mais importante deste ficheiro.**

    A Ana tem o negócio dela **e** um demo. Reinicializar o demo não lhe pode
    tirar o negócio — e se o filtro `is_demo` do
    `_revogar_demonstracoes_anteriores` falhasse, era exactamente isso que
    acontecia: um comando de operador a cortar o acesso de alguém à sua própria
    casa, em silêncio, com a mensagem de sucesso no ecrã.

    É por isso que a comparação é por igualdade a `True` e não por ausência de
    nada, e é por isso que este teste tem os dois tipos de estabelecimento na
    mesma conta.
    """
    a_serio = criar_tenant(name="Pastelaria Aurora")
    with tenant_scope(a_serio.id):
        conceder_pertenca(
            user=ana, tenant_id=a_serio.id, role=Papel.OWNER, display_name="Ana"
        )
    primeiro_demo = _semear().tenant.id

    segundo = _semear()

    assert segundo.revogados == (primeiro_demo,), "só o demo foi revogado"

    ana.refresh_from_db(fields=["tenant_ids"])
    assert set(ana.tenant_ids) == {a_serio.id, segundo.tenant.id}

    # E o acesso ao negócio continua a funcionar ponta a ponta.
    sessao = _cliente(ana, a_serio.id).get(URL_SESSAO).json()
    assert sessao["tenant_ativo"] == {
        "id": str(a_serio.id),
        "nome": "Pastelaria Aurora",
        "papel": Papel.OWNER.value,
        "demonstracao": False,
    }


# ---------------------------------------------------------------------------
# 4. A bandeira viaja no contrato, nos dois sítios
# ---------------------------------------------------------------------------


def test_a_bandeira_viaja_no_tenant_ativo_e_na_lista(ana: User) -> None:
    """Os dois sítios, porque o cromado precisa dos dois.

    A faixa permanente da barra de topo lê o `tenant_ativo.demonstracao`; o item
    marcado no seletor lê o de **cada entrada** de `tenants`. Uma resposta que só
    trouxesse um dos dois dava um cromado a meio: ou a faixa sem o item marcado,
    ou o contrário.
    """
    a_serio = criar_tenant(name="Pastelaria Aurora")
    with tenant_scope(a_serio.id):
        conceder_pertenca(
            user=ana, tenant_id=a_serio.id, role=Papel.OWNER, display_name="Ana"
        )
    demo = _semear().tenant.id

    sessao = _cliente(ana, demo).get(URL_SESSAO).json()

    assert sessao["tenant_ativo"]["demonstracao"] is True
    por_id = {entrada["id"]: entrada["demonstracao"] for entrada in sessao["tenants"]}
    assert por_id == {str(demo): True, str(a_serio.id): False}


# ---------------------------------------------------------------------------
# 5. Lá dentro é um estabelecimento como qualquer outro
# ---------------------------------------------------------------------------


def test_o_menu_do_demo_e_o_menu_de_qualquer_estabelecimento(ana: User) -> None:
    """Decisão 1: "nenhum endpoint sabe que ele existe. Zero ramos."

    O menu de um `owner` num demo é o mesmo de um `owner` em qualquer outro
    estabelecimento — oito itens, os defaults do registo, sem linha nenhuma na
    tabela. Se algum dia alguém esconder um item "porque é o demo", é aqui que
    aparece.
    """
    demo = _semear().tenant.id

    sessao = _cliente(ana, demo).get(URL_SESSAO).json()

    assert sessao["estado"] == "ativa"
    assert [item["route_id"] for item in sessao["menu"]] == [
        "inicio",
        "painel",
        "alertas",
        "stock",
        "contar",
        "receber",
        "convites",
        "configuracao",
    ]
