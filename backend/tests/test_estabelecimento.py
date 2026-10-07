"""A configuração do estabelecimento, ponta a ponta (ADR 0017).

Este ficheiro mede cinco coisas, e as três primeiras não se vêem por revisão.

**1. O IDOR é impossível por construção e não por verificação.** Não há `pk` no
path nem no corpo: qual é o estabelecimento decide-se no âmbito que o middleware
abre a partir da sessão, e o service faz `Tenant.objects.get()` **sem filtro**
porque a política do `accounts_tenant` compara `id` com o GUC. A prova é dupla e
nos dois sentidos: dois `owner` de dois estabelecimentos leem e escrevem coisas
diferentes pelo **mesmo** URL (`test_dois_owners_leem_o_seu_estabelecimento_pelo_mesmo_url`),
e a escrita de um não toca na linha do outro.

**2. A janela do dia de negócio é recusada em dois sítios, e os dois contam.** O
serializer dá 400 com a frase que aparece debaixo do campo; a `CheckConstraint` da
migração 0009 é a rede, e é testada **por baixo do HTTP**
(`test_a_base_de_dados_recusa_uma_hora_fora_da_janela`) porque uma rede que nunca
foi tocada não se sabe se existe. Um dia de negócio às 16:00 parte todos os dias
em dois em silêncio, e silêncio é o modo de falha que esta casa não aceita.

**3. O `is_demo` torna o nome só de leitura, e mais nada.** O resto da
configuração muda no estabelecimento de demonstração — é a propriedade que a ADR
0018 quer (o demo comporta-se como o real) — e é por isso que há um teste para
cada metade.

**4. `owner` em leitura e em escrita, com 403 e não 200 parcial** (ADR 0017,
decisão 3). Medido para os três papéis e para os dois métodos.

**5. A hora atravessa o contrato como `"HH:MM"`** e não `"HH:MM:SS"`, que é o
default do DRF. Parece cosmético e não é: é o que um `<input type="time">`
consome, e um segundo par de caracteres que é sempre `00` seria ruído num valor
que a pessoa lê e escreve.

## Porque é que todos levam `transactional_db`

A razão dos outros ficheiros: com a transação do pytest-django por fora, o
`set_config('app.tenant_id', ..., true)` que o `tenant_scope` corre só reverte no
fim **dela** e não no fim do bloco `with`. As asserções sobre o que se vê fora de
âmbito passariam a medir um âmbito ainda aberto — e este ficheiro tem duas.

## O guarda de âmbito do `conftest.py` está a trabalhar aqui

Nenhum teste tem a marca `sem_ambito_de_rls`. Como cada `GET /estabelecimento` lê
o `accounts_tenant`, que tem política, **cada** pedido deste ficheiro é também uma
afirmação de que a leitura acontece dentro de um âmbito: sem ele, o `get()` sem
filtro levantava `Tenant.DoesNotExist` em vez de devolver a linha de outra pessoa
— e é isso que o `test_fora_de_ambito_nao_se_le_estabelecimento_nenhum` fixa.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import time
from typing import Any
from uuid import UUID

import pytest
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import Client

from apps.accounts.middleware import SESSION_TENANT_KEY
from apps.accounts.models import Papel, RegimeDeIva, Tenant, User
from apps.accounts.services import (
    BACKEND_DE_SESSAO,
    conceder_pertenca,
    criar_tenant,
)
from apps.shared.db import tenant_scope

URL_ESTABELECIMENTO = "/api/v1/estabelecimento"

#: O default da coluna, afirmado aqui para o teste do `PATCH` ter com que
#: contrastar. Vem da migração 0008 e é **hipótese** e não resposta de um
#: utilizador real: a hora exacta é a Q6 da sessão 0.
HORA_POR_OMISSAO = "04:00"


@dataclass(frozen=True, kw_only=True, slots=True)
class Cenario:
    """Dois estabelecimentos reais, um de demonstração, e um papel por teste."""

    alfa: Tenant
    beta: Tenant
    demo: Tenant
    #: `owner` em Alfa.
    ana: User
    #: `manager` em Alfa: o papel que a Q7 não resolveu, e que aqui leva 403.
    bento: User
    #: `staff` em Alfa.
    clara: User
    #: `owner` em Beta: é ele que prova que o URL é o mesmo e a linha não.
    dinis: User
    #: `owner` do estabelecimento de demonstração.
    elsa: User


@pytest.fixture(autouse=True)
def _cache_limpa() -> Iterator[None]:
    """O throttle do DRF conta em cache, e a cache é local ao processo."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def cenario(transactional_db: None) -> Cenario:
    """O cenário, construído **só** pelas funções de `services.py`.

    A excepção é o `is_demo`, escrito com um `update` dentro do âmbito: não há
    service para o pôr, e é de propósito — o estabelecimento de demonstração
    nasce do seeder da ADR 0018, que ainda não existe. Quando existir, esta linha
    é substituída pela chamada a ele e o teste não muda.
    """
    ana = User.objects.create_user("ana@alfa.pt")
    bento = User.objects.create_user("bento@alfa.pt")
    clara = User.objects.create_user("clara@alfa.pt")
    dinis = User.objects.create_user("dinis@beta.pt")
    elsa = User.objects.create_user("elsa@demo.pt")

    alfa = criar_tenant(name="Pastelaria Alfa")
    beta = criar_tenant(name="Café Beta")
    demo = criar_tenant(name="Pastelaria Modelo (demonstração)")

    with tenant_scope(alfa.id):
        conceder_pertenca(user=ana, tenant_id=alfa.id, role=Papel.OWNER, display_name="Ana")
        conceder_pertenca(
            user=bento, tenant_id=alfa.id, role=Papel.MANAGER, display_name="Bento"
        )
        conceder_pertenca(user=clara, tenant_id=alfa.id, role=Papel.STAFF, display_name="Clara")
    with tenant_scope(beta.id):
        conceder_pertenca(user=dinis, tenant_id=beta.id, role=Papel.OWNER, display_name="Dinis")
    with tenant_scope(demo.id):
        conceder_pertenca(user=elsa, tenant_id=demo.id, role=Papel.OWNER, display_name="Elsa")
        Tenant.objects.filter(pk=demo.id).update(is_demo=True)

    return Cenario(
        alfa=alfa, beta=beta, demo=demo, ana=ana, bento=bento, clara=clara, dinis=dinis, elsa=elsa
    )


def _cliente(user: User | None = None, tenant_id: UUID | None = None, **kwargs: Any) -> Client:
    cliente = Client(**kwargs)
    if user is not None:
        cliente.force_login(user, backend=BACKEND_DE_SESSAO)
    if tenant_id is not None:
        sessao = cliente.session
        sessao[SESSION_TENANT_KEY] = str(tenant_id)
        sessao.save()
    return cliente


def _guardar(cliente: Client, **campos: Any) -> Any:
    """`PATCH` com os três campos. O corpo inteiro, que é o que o contrato pede."""
    corpo = {
        "nome": "Pastelaria Alfa",
        "vat_regime": RegimeDeIva.NORMAL,
        "business_day_starts_at": HORA_POR_OMISSAO,
        **campos,
    }
    return cliente.patch(URL_ESTABELECIMENTO, data=corpo, content_type="application/json")


def _linha(tenant_id: UUID) -> Tenant:
    """A linha, relida **dentro do âmbito** dela: a tabela tem política."""
    with tenant_scope(tenant_id):
        return Tenant.objects.get()


# ---------------------------------------------------------------------------
# 1. O caminho feliz, e a forma do contrato
# ---------------------------------------------------------------------------


def test_o_owner_le_a_configuracao_do_seu_estabelecimento(cenario: Cenario) -> None:
    """Os cinco campos, e os defaults da migração 0008."""
    resposta = _cliente(cenario.ana, cenario.alfa.id).get(URL_ESTABELECIMENTO)

    assert resposta.status_code == 200, resposta.content
    assert resposta.json() == {
        "id": str(cenario.alfa.id),
        "nome": "Pastelaria Alfa",
        "vat_regime": RegimeDeIva.NORMAL.value,
        "business_day_starts_at": HORA_POR_OMISSAO,
        "demonstracao": False,
    }


def test_a_hora_viaja_sem_segundos(cenario: Cenario) -> None:
    """`"05:30"` e não `"05:30:00"`, nos dois sentidos.

    O default do DRF para um `TimeField` é `"%H:%M:%S"`, logo isto seria o
    comportamento se ninguém o tivesse escolhido — e um `<input type="time">`
    recebe `"05:30:00"` sem reclamar e devolve `"05:30"`, pelo que o primeiro
    `PATCH` depois de carregar o ecrã mudava o valor sem ninguém lhe tocar.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    resposta = _guardar(cliente, business_day_starts_at="05:30")

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["business_day_starts_at"] == "05:30"
    assert cliente.get(URL_ESTABELECIMENTO).json()["business_day_starts_at"] == "05:30"
    assert _linha(cenario.alfa.id).business_day_starts_at == time(5, 30)


def test_o_patch_guarda_os_tres_campos(cenario: Cenario) -> None:
    """O corpo inteiro, e a resposta é a configuração como ficou."""
    resposta = _guardar(
        _cliente(cenario.ana, cenario.alfa.id),
        nome="Pastelaria Aurora",
        vat_regime=RegimeDeIva.ISENTO_ART_53,
        business_day_starts_at="02:00",
    )

    assert resposta.status_code == 200, resposta.content
    linha = _linha(cenario.alfa.id)
    assert linha.name == "Pastelaria Aurora"
    assert linha.vat_regime == RegimeDeIva.ISENTO_ART_53
    assert linha.business_day_starts_at == time(2, 0)


def test_o_regime_viaja_pelos_dois_valores_e_nao_tem_terceiro(cenario: Cenario) -> None:
    """Os dois valores do enum, e a recusa de um terceiro plausível.

    `art_60` é o caso que o `domain-expert` descartou por ser **inaplicável à
    restauração** (exige revenda sem transformação ≥ 90%), e é precisamente o
    valor que alguém acrescentaria "por precaução". Um valor que ninguém pode
    escolher é um ramo que ninguém testa — e este teste é o que torna
    acrescentá-lo uma decisão visível em vez de uma linha num enum.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    for regime in (RegimeDeIva.NORMAL, RegimeDeIva.ISENTO_ART_53):
        assert _guardar(cliente, vat_regime=regime).status_code == 200

    recusado = _guardar(cliente, vat_regime="art_60")
    assert recusado.status_code == 400, recusado.content
    assert "vat_regime" in recusado.json()


# ---------------------------------------------------------------------------
# 2. O isolamento: o mesmo URL, linhas diferentes
# ---------------------------------------------------------------------------


def test_dois_owners_leem_o_seu_estabelecimento_pelo_mesmo_url(cenario: Cenario) -> None:
    """A prova de que o âmbito é que decide, e não um id no pedido.

    O `GET` não leva id nenhum. Dois donos, dois estabelecimentos, o **mesmo**
    URL, duas respostas — e é o `tenant_id` da sessão que as separa, através da
    política. Não há aqui uma comparação a fazer nem um `pk` para rejeitar.
    """
    de_alfa = _cliente(cenario.ana, cenario.alfa.id).get(URL_ESTABELECIMENTO).json()
    de_beta = _cliente(cenario.dinis, cenario.beta.id).get(URL_ESTABELECIMENTO).json()

    assert de_alfa["id"] == str(cenario.alfa.id)
    assert de_beta["id"] == str(cenario.beta.id)
    assert de_alfa["nome"] == "Pastelaria Alfa"
    assert de_beta["nome"] == "Café Beta"


def test_a_escrita_de_um_owner_nao_toca_no_estabelecimento_do_outro(
    cenario: Cenario,
) -> None:
    """A outra metade: o `UPDATE` também é filtrado pela política."""
    _guardar(
        _cliente(cenario.ana, cenario.alfa.id),
        nome="Alfa, mudada",
        business_day_starts_at="01:00",
    )

    beta = _linha(cenario.beta.id)
    assert beta.name == "Café Beta"
    assert beta.business_day_starts_at == time(4, 0)
    assert beta.vat_regime == RegimeDeIva.NORMAL


@pytest.mark.sem_ambito_de_rls
def test_fora_de_ambito_nao_se_le_estabelecimento_nenhum(cenario: Cenario) -> None:
    """O `get()` sem filtro falha **fechado** quando não há âmbito.

    **A marca `sem_ambito_de_rls` é o que este teste é**, e não uma dispensa por
    conveniência: o guarda do `conftest.py` levanta em qualquer query a uma tabela
    com política fora de âmbito, precisamente para nenhum teste medir um zero que
    vem da política em vez de vir dos dados. Aqui a leitura sem âmbito **é** o
    objecto do teste, que é o único caso em que a marca se usa — e a mensagem do
    guarda di-lo por escrito.

    É o modo de falha que torna o `Tenant.objects.get()` do service seguro de
    escrever: fora de âmbito a política não deixa ver linha nenhuma, logo o
    `get()` levanta `DoesNotExist` — alto e imediatamente — em vez de devolver a
    primeira linha da tabela, que seria a configuração de outra pessoa.
    """
    with pytest.raises(Tenant.DoesNotExist):
        Tenant.objects.get()


# ---------------------------------------------------------------------------
# 3. A janela do dia de negócio: a mensagem e a rede
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("hora", ["00:00", "03:45", "06:00"])
def test_as_horas_dentro_da_janela_sao_aceites(cenario: Cenario, hora: str) -> None:
    """Os dois extremos e um valor com minutos que não são 0 nem 30.

    O `03:45` está aqui de propósito: a constraint afirma a **janela** e não o
    passo, porque uma casa que queira as 03:45 não tem nada de errado — o passo
    é do controlo no ecrã e não uma regra de domínio.
    """
    resposta = _guardar(_cliente(cenario.ana, cenario.alfa.id), business_day_starts_at=hora)

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["business_day_starts_at"] == hora


@pytest.mark.parametrize("hora", ["06:01", "12:00", "16:00", "23:59"])
def test_uma_hora_fora_da_janela_e_400_no_campo(cenario: Cenario, hora: str) -> None:
    """400 com a chave `business_day_starts_at`, e a linha intacta.

    O `16:00` é o valor que o `domain-expert` nomeou: não é uma preferência, é um
    erro de dedo que parte todos os dias em dois sem ninguém ver.
    """
    resposta = _guardar(_cliente(cenario.ana, cenario.alfa.id), business_day_starts_at=hora)

    assert resposta.status_code == 400, resposta.content
    assert "business_day_starts_at" in resposta.json()
    assert _linha(cenario.alfa.id).business_day_starts_at == time(4, 0)


def test_a_base_de_dados_recusa_uma_hora_fora_da_janela(cenario: Cenario) -> None:
    """A rede, medida por baixo do HTTP — e é por isso que este teste existe.

    O 400 do serializer prova que a **mensagem** funciona. Isto prova que a
    `CheckConstraint` da migração 0009 existe e morde: uma escrita que não passe
    pelo serializer — um shell, um comando de gestão, um fixture — não consegue
    pôr lá as 16:00. Uma rede que nunca foi tocada não se sabe se está lá.
    """
    with tenant_scope(cenario.alfa.id):
        with pytest.raises(IntegrityError, match="tenant_dia_de_negocio_entre_0_e_6"):
            with transaction.atomic():
                Tenant.objects.filter(pk=cenario.alfa.id).update(
                    business_day_starts_at=time(16, 0)
                )


# ---------------------------------------------------------------------------
# 4. O estabelecimento de demonstração
# ---------------------------------------------------------------------------


def test_o_demo_diz_que_e_demo(cenario: Cenario) -> None:
    """O campo `demonstracao` é o que permite ao ecrã avisar quem lá está."""
    resposta = _cliente(cenario.elsa, cenario.demo.id).get(URL_ESTABELECIMENTO)

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["demonstracao"] is True


def test_o_nome_do_demo_nao_se_altera(cenario: Cenario) -> None:
    """400 no campo `nome`, e a linha intacta.

    A razão é da sessão 0 e não técnica: um nome editável no estabelecimento de
    demonstração deixa o dono escrever lá o nome da pastelaria **dele**, e aí os
    dados semeados passam a parecer os dele — é a proibição nº 12 do guião a ser
    quebrada pelo próprio utilizador, com a app a ajudar.
    """
    resposta = _guardar(
        _cliente(cenario.elsa, cenario.demo.id), nome="Pastelaria do Tomás"
    )

    assert resposta.status_code == 400, resposta.content
    assert "nome" in resposta.json()
    assert _linha(cenario.demo.id).name == "Pastelaria Modelo (demonstração)"


def test_o_resto_da_configuracao_muda_no_demo(cenario: Cenario) -> None:
    """A outra metade, e é ela que faz o demo valer para o que foi feito.

    A ADR 0018 quer um estabelecimento que **se comporta** como o real: se o
    `PATCH` inteiro fosse recusado, experimentar a configuração no demo era
    impossível — e configurar é uma das coisas que se vai lá experimentar.
    """
    resposta = _guardar(
        _cliente(cenario.elsa, cenario.demo.id),
        nome="Pastelaria Modelo (demonstração)",
        vat_regime=RegimeDeIva.ISENTO_ART_53,
        business_day_starts_at="05:00",
    )

    assert resposta.status_code == 200, resposta.content
    linha = _linha(cenario.demo.id)
    assert linha.vat_regime == RegimeDeIva.ISENTO_ART_53
    assert linha.business_day_starts_at == time(5, 0)
    assert linha.is_demo is True


def test_o_is_demo_nao_se_escreve_pelo_contrato(cenario: Cenario) -> None:
    """Um `demonstracao` no corpo é ignorado, nos dois sentidos.

    O campo não existe no `EstabelecimentoInSerializer`, logo o DRF ignora-o. O
    que esta asserção fecha é que ele é **ignorado e não obedecido** — o dia em
    que alguém o acrescentasse ao serializer era o dia em que um estabelecimento
    real podia ser marcado como demonstração (esconder dados reais atrás de um
    aviso de "isto é de brincar") ou o demo promovido a real (dados semeados a
    passar por dados de negócio).
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    assert _guardar(cliente, demonstracao=True).status_code == 200
    assert _linha(cenario.alfa.id).is_demo is False

    # O `nome` vai o da linha do demo: o helper manda os três campos e um nome
    # diferente dispararia a recusa do demo, que é outro teste. Enviar o nome
    # igual ao que está é aceite de propósito — ver `guardar_estabelecimento`.
    no_demo = _guardar(
        _cliente(cenario.elsa, cenario.demo.id),
        nome="Pastelaria Modelo (demonstração)",
        demonstracao=False,
    )
    assert no_demo.status_code == 200, no_demo.content
    assert _linha(cenario.demo.id).is_demo is True


# ---------------------------------------------------------------------------
# 5. Quem pode: `owner` em leitura e em escrita
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("papel", [Papel.MANAGER, Papel.STAFF])
def test_quem_nao_e_owner_leva_403_na_leitura_e_na_escrita(
    cenario: Cenario, papel: str
) -> None:
    """403 e **não** 200 parcial, nos dois métodos (ADR 0017, decisão 3).

    Num ecrã de configurações um 200 parcial torna "não podes ver isto"
    indistinguível de "esta empresa ainda não configurou nada", e os dois
    precisam de ecrãs opostos: o vazio ensina a configurar, o restrito não pode.

    O `manager` está aqui porque é a Q7 — "um `manager` configura a empresa?"
    está marcada como *não inventes default sem falar com um utilizador real*, e
    o conjunto `{owner}` alarga-se sem se desfazer. Hoje a resposta é 403, e este
    teste é onde ela aparece no diff no dia em que mudar.
    """
    user = cenario.bento if papel == Papel.MANAGER else cenario.clara
    cliente = _cliente(user, cenario.alfa.id)

    assert cliente.get(URL_ESTABELECIMENTO).status_code == 403
    assert _guardar(cliente, nome="Tentativa").status_code == 403
    assert _linha(cenario.alfa.id).name == "Pastelaria Alfa"


def test_um_anonimo_leva_403(cenario: Cenario) -> None:
    """Sem sessão não há âmbito, e sem âmbito não há estabelecimento."""
    assert _cliente().get(URL_ESTABELECIMENTO).status_code == 403


def test_uma_sessao_sem_estabelecimento_escolhido_leva_403(cenario: Cenario) -> None:
    """O `PertenceAoTenant` nega quando não há `request.tenant`.

    É o caso de quem fez login e ainda não escolheu — e a diferença em relação ao
    `/auth/preferencias` é exactamente esta: o tema troca-se nesse estado (é da
    pessoa), a configuração da empresa não (não se sabe de que empresa).
    """
    assert _cliente(cenario.ana).get(URL_ESTABELECIMENTO).status_code == 403


@pytest.mark.parametrize("metodo", ["post", "put", "delete"])
def test_a_rota_so_responde_a_get_e_patch(cenario: Cenario, metodo: str) -> None:
    """405 nos outros três. Não há `POST`: o estabelecimento já existe.

    Criar um estabelecimento é o comando `criar_estabelecimento` e não um
    endpoint — a ADR 0007 decidiu que quem cria um tenant o faz com o papel de
    `owner` concedido na mesma transação, e isso não é uma operação que alguém com
    sessão faça a partir de um ecrã.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    resposta = getattr(cliente, metodo)(
        URL_ESTABELECIMENTO, data={}, content_type="application/json"
    )

    assert resposta.status_code == 405, resposta.content


def test_sem_token_de_csrf_o_patch_e_recusado(cenario: Cenario) -> None:
    """O `csrf_protect` desta view, medido — e a razão de ele cá estar.

    É redundante hoje (o `SessionAuthentication` já verifica o token num pedido
    autenticado) e fica porque esta view escreve configuração de uma empresa
    inteira: o `as_view()` do DRF embrulha tudo em `csrf_exempt`, e a protecção
    depende de o `SessionAuthentication` correr e **encontrar** utilizador. No dia
    em que aqui entrar uma autenticação por token, a diferença é esta linha.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id, enforce_csrf_checks=True)

    sem_token = _guardar(cliente, nome="Sem token")

    assert sem_token.status_code == 403
    assert _linha(cenario.alfa.id).name == "Pastelaria Alfa"
