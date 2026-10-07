"""A preferência de tema, ponta a ponta (ADR 0016).

É um endpoint com um campo, e ainda assim tem ficheiro próprio: o que se mede
aqui não é "guardar um `varchar`" — são quatro propriedades que a ADR pede pelo
nome e que não se vêem por revisão.

**1. O `PATCH` de uma conta não altera o tema de outra, e não há argumento para
o tentar.** O corpo não tem `user_id` (`PreferenciasInSerializer`), logo a prova
tem duas metades: um campo a mais no corpo é **ignorado** em vez de obedecido
(`test_um_user_id_no_corpo_e_ignorado_e_nao_toca_na_outra_conta`), e a conta de
quem pede é a única que muda. Sem a primeira metade, o dia em que alguém
acrescentasse `user_id` ao serializer era o dia em que isto passava a ser um
IDOR sem nenhum teste a cair.

**2. Dispensado de âmbito, e ainda assim protegido de CSRF.** É a afirmação mais
arriscada da ADR 0016, porque é uma **ausência**: esta view não leva
`csrf_protect`, ao contrário do login e da activação, e a razão escrita é que o
`SessionAuthentication` verifica o token quando encontra utilizador na sessão.
Uma afirmação sobre o que acontece por omissão é exactamente o tipo de coisa que
se escreve com confiança e está errada, por isso está medida nas duas metades
com `enforce_csrf_checks=True`
(`test_sem_token_de_csrf_o_patch_e_recusado_e_o_tema_nao_muda`). Se um dia o DRF
mudar de comportamento, cai aqui e não em produção.

**3. Funciona nos estados em que ainda não há estabelecimento.** `escolha_pendente`
e `sem_estabelecimento` são os dois ecrãs onde o relâmpago da primeira pintura se
vê, e um tema que só se trocasse depois de escolher o estabelecimento era um tema
que não se trocava onde é preciso. Daí não haver `PertenceAoTenant` na view, e daí
os dois testes que atravessam esses estados.

**4. Um valor fora dos três é um 400 por campo e não um tema inválido guardado.**
A coluna é lida pelo cliente e copiada para `localStorage`; o valor ser fechado a
três é o que torna essa cópia segura.

## Porque é que todos levam `transactional_db`

A razão do `tests/test_autenticacao.py`, e aqui com uma a mais: o caminho da
resposta é o `sessao_atual`, que abre um âmbito por candidato para confirmar a
pertença. Com a transação do pytest-django por fora, o
`set_config('app.tenant_id', ..., true)` só revertia no fim **dela**, e as
asserções sobre o que se lê fora de âmbito mediriam um âmbito ainda aberto.

## O guarda de âmbito do `conftest.py` está a trabalhar neste ficheiro

Nenhum teste tem a marca `sem_ambito_de_rls`. Como a resposta de cada `PATCH` é
um `SessaoOut` completo — e montá-lo lê o `accounts_membership` e o
`accounts_tenant` —, cada teste aqui é também uma afirmação de que essas leituras
acontecem **dentro** de `tenant_scope`. A escrita do `tema`, essa, é na tabela
sem política e não precisa de âmbito nenhum: é o que a torna disponível em
`escolha_pendente`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client

from apps.accounts.middleware import SESSION_TENANT_KEY
from apps.accounts.models import Papel, Tema, Tenant, User
from apps.accounts.services import (
    BACKEND_DE_SESSAO,
    EstadoDaSessao,
    conceder_pertenca,
    criar_tenant,
)
from apps.shared.db import tenant_scope

URL_PREFERENCIAS = "/api/v1/auth/preferencias"
URL_SESSAO = "/api/v1/auth/sessao"

#: A mesma razão de nome do `test_autenticacao.py`: o `S105` do ruff trata um
#: literal atribuído a um nome com "password" dentro como credencial em código.
CREDENCIAL_VALIDA = "trigo-fresco-ao-amanhecer-7"


@dataclass(frozen=True, kw_only=True, slots=True)
class Cenario:
    """Uma conta por estado da sessão em que o tema tem de se poder trocar."""

    alfa: Tenant
    beta: Tenant
    #: `owner` em Alfa e em mais nada: chega a `ativa` sem escolher nada.
    ana: User
    #: `staff` nos dois: fica em `escolha_pendente` depois do login.
    carla: User
    #: Sem pertença em sítio nenhum: `sem_estabelecimento`.
    bruno: User


@pytest.fixture(autouse=True)
def _cache_limpa() -> Iterator[None]:
    """O throttle do DRF conta em cache, e a cache é local ao processo."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def cenario(transactional_db: None) -> Cenario:
    """O cenário, construído **só** pelas funções de `services.py`."""
    ana = User.objects.create_user("ana@alfa.pt", CREDENCIAL_VALIDA)
    carla = User.objects.create_user("carla@contabilidade.pt", CREDENCIAL_VALIDA)
    bruno = User.objects.create_user("bruno@sem-pertenca.pt", CREDENCIAL_VALIDA)

    alfa = criar_tenant(name="Pastelaria Alfa")
    beta = criar_tenant(name="Café Beta")

    with tenant_scope(alfa.id):
        conceder_pertenca(
            user=ana, tenant_id=alfa.id, role=Papel.OWNER, display_name="Ana Silva"
        )
        conceder_pertenca(
            user=carla,
            tenant_id=alfa.id,
            role=Papel.STAFF,
            display_name="Carla (contabilidade)",
        )
    with tenant_scope(beta.id):
        conceder_pertenca(
            user=carla, tenant_id=beta.id, role=Papel.STAFF, display_name="Carla"
        )

    return Cenario(alfa=alfa, beta=beta, ana=ana, carla=carla, bruno=bruno)


def _cliente(user: User | None = None, tenant_id: UUID | None = None, **kwargs: Any) -> Client:
    """Um cliente, com (ou sem) sessão e com (ou sem) estabelecimento ativo."""
    cliente = Client(**kwargs)
    if user is not None:
        cliente.force_login(user, backend=BACKEND_DE_SESSAO)
    if tenant_id is not None:
        sessao = cliente.session
        sessao[SESSION_TENANT_KEY] = str(tenant_id)
        sessao.save()
    return cliente


def _guardar(cliente: Client, corpo: dict[str, Any], **kwargs: Any) -> Any:
    """`PATCH` com corpo JSON, que é o único que esta view aceita."""
    return cliente.patch(
        URL_PREFERENCIAS, data=corpo, content_type="application/json", **kwargs
    )


def _tema_na_base(user: User) -> str:
    """O que está na coluna, relido. O `accounts_user` não tem política (ADR 0007)."""
    return User.objects.values_list("tema", flat=True).get(pk=user.pk)


# ---------------------------------------------------------------------------
# 1. O default, e o caminho feliz
# ---------------------------------------------------------------------------


def test_uma_conta_nova_prefere_o_escuro(cenario: Cenario) -> None:
    """O default é a identidade aprovada e não a configuração do portátil.

    Vale um teste porque é o valor que **todas** as contas de hoje têm e porque
    é a razão pela qual a ADR 0016 recusou um quarto estado `sistema`: a
    preferência do sistema é binária e as paletas são três.
    """
    assert cenario.ana.tema == Tema.ESCURO
    assert _tema_na_base(cenario.ana) == Tema.ESCURO


@pytest.mark.parametrize("tema", [Tema.CLARO, Tema.MEIO_TERMO, Tema.ESCURO])
def test_os_tres_temas_guardam_e_voltam_na_sessao(cenario: Cenario, tema: str) -> None:
    """Os três, e não só o que não é o default.

    Parametrizado contra os valores do enum e não contra uma lista escrita aqui:
    uma paleta nova no `Tema` entra nestes casos sem ninguém a inscrever, que é
    o contrário de um teste que passa por não conhecer o valor novo.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    resposta = _guardar(cliente, {"tema": tema})

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["utilizador"]["tema"] == tema
    assert _tema_na_base(cenario.ana) == tema


def test_o_tema_guardado_viaja_no_get_da_sessao(cenario: Cenario) -> None:
    """A decisão 2 da ADR 0016, medida do lado do cliente.

    O `PATCH` devolver o tema não prova que ele viaja: o que o arranque da SPA
    lê é o `GET /auth/sessao`, e é lá que a cópia local se alimenta. Um
    `SessaoOut` com `tema` numa resposta e sem ele na outra era precisamente o
    bug que não se vê em revisão.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    _guardar(cliente, {"tema": Tema.CLARO})

    sessao = cliente.get(URL_SESSAO).json()

    assert sessao["estado"] == EstadoDaSessao.ATIVA
    assert sessao["utilizador"]["tema"] == Tema.CLARO


# ---------------------------------------------------------------------------
# 2. Uma conta não mexe no tema de outra
# ---------------------------------------------------------------------------


def test_um_user_id_no_corpo_e_ignorado_e_nao_toca_na_outra_conta(
    cenario: Cenario,
) -> None:
    """A primeira metade da prova que a ADR 0016 pede.

    O corpo não tem `user_id`, logo um `user_id` enviado é um campo
    desconhecido: o `Serializer` do DRF ignora-o, e o que esta asserção fecha é
    que ele é ignorado **e não obedecido**. A segunda metade é a conta da Carla
    ficar no default — se o campo alguma vez passar a ser lido, é aqui que se vê.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    resposta = _guardar(
        cliente, {"tema": Tema.CLARO, "user_id": str(cenario.carla.pk)}
    )

    assert resposta.status_code == 200, resposta.content
    assert _tema_na_base(cenario.ana) == Tema.CLARO
    assert _tema_na_base(cenario.carla) == Tema.ESCURO


def test_duas_contas_do_mesmo_estabelecimento_tem_temas_independentes(
    cenario: Cenario,
) -> None:
    """A afirmação de produto da ADR 0016: a preferência é da pessoa.

    Duas pessoas no **mesmo** estabelecimento, com temas diferentes ao mesmo
    tempo. É o teste que falharia se alguém movesse a coluna para o `Tenant` ou
    para o `Membership` — as duas alternativas que a ADR rejeitou.
    """
    _guardar(_cliente(cenario.ana, cenario.alfa.id), {"tema": Tema.CLARO})
    _guardar(_cliente(cenario.carla, cenario.alfa.id), {"tema": Tema.MEIO_TERMO})

    assert _tema_na_base(cenario.ana) == Tema.CLARO
    assert _tema_na_base(cenario.carla) == Tema.MEIO_TERMO


def test_a_mesma_pessoa_tem_o_mesmo_tema_nos_dois_estabelecimentos(
    cenario: Cenario,
) -> None:
    """O outro lado da mesma decisão, e a razão de não ser no `Membership`.

    A Carla é `staff` em Alfa e em Beta. Troca o tema com Alfa ativo e lê-o com
    Beta ativo: é o mesmo. Se a coluna vivesse no `Membership`, a app mudava de
    aspecto ao trocar de estabelecimento.
    """
    _guardar(_cliente(cenario.carla, cenario.alfa.id), {"tema": Tema.MEIO_TERMO})

    em_beta = _cliente(cenario.carla, cenario.beta.id).get(URL_SESSAO).json()

    assert em_beta["tenant_ativo"]["id"] == str(cenario.beta.id)
    assert em_beta["utilizador"]["tema"] == Tema.MEIO_TERMO


# ---------------------------------------------------------------------------
# 3. Os estados em que ainda não há estabelecimento
# ---------------------------------------------------------------------------


def test_troca_se_o_tema_em_escolha_pendente(cenario: Cenario) -> None:
    """Sessão sem estabelecimento escolhido, e dois para escolher.

    É um dos dois ecrãs onde o relâmpago se vê, e é a razão de a view ser
    dispensada de âmbito. Com `PertenceAoTenant` na lista, isto era um 403.
    """
    cliente = _cliente(cenario.carla)

    resposta = _guardar(cliente, {"tema": Tema.CLARO})

    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    assert corpo["estado"] == EstadoDaSessao.ESCOLHA_PENDENTE
    assert corpo["tenant_ativo"] is None
    assert corpo["utilizador"]["tema"] == Tema.CLARO


def test_troca_se_o_tema_sem_estabelecimento_nenhum(cenario: Cenario) -> None:
    """O outro ecrã sem âmbito: uma conta sem pertença em sítio nenhum.

    O `bruno` existe no `accounts_user` e não é membro de nada. Saber um email
    não compra nada (ADR 0007), e trocar de tema também não — mas tem de
    funcionar, porque é o ecrã que ele vê.
    """
    cliente = _cliente(cenario.bruno)

    resposta = _guardar(cliente, {"tema": Tema.MEIO_TERMO})

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["estado"] == EstadoDaSessao.SEM_ESTABELECIMENTO
    assert _tema_na_base(cenario.bruno) == Tema.MEIO_TERMO


# ---------------------------------------------------------------------------
# 4. O que a view recusa
# ---------------------------------------------------------------------------


def test_um_pedido_anonimo_e_recusado(cenario: Cenario) -> None:
    """`IsAuthenticated`, e é o que faz o CSRF ser verificado no caso que resta.

    403 e não 200: ao contrário do `GET /auth/sessao`, aqui não há resposta
    honesta para quem não tem sessão — não há conta onde escrever.
    """
    resposta = _guardar(_cliente(), {"tema": Tema.CLARO})

    assert resposta.status_code == 403
    assert _tema_na_base(cenario.ana) == Tema.ESCURO


@pytest.mark.parametrize(
    "tema", ["", "sistema", "dark", "ESCURO", "meio-termo", "escuro; DROP TABLE"]
)
def test_um_tema_fora_dos_tres_e_400_por_campo(cenario: Cenario, tema: str) -> None:
    """400 com a chave `tema`, e a coluna intacta.

    Os casos não são aleatórios: `sistema` é o quarto estado que a ADR recusou,
    `dark` é o nome em inglês que um cliente escreveria de cabeça, `ESCURO` é a
    caixa errada, `meio-termo` é o hífen em vez do underscore (o erro mais
    provável, porque o CSS usa `data-tema="meio_termo"` e os paths desta API usam
    hífen), e o último é a razão pela qual isto é um `ChoiceField` e não um
    `CharField` — não porque haja SQL dinâmico, mas porque o valor é escrito num
    atributo do DOM pelo cliente.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    resposta = _guardar(cliente, {"tema": tema})

    assert resposta.status_code == 400, resposta.content
    assert "tema" in resposta.json()
    assert _tema_na_base(cenario.ana) == Tema.ESCURO


def test_um_corpo_sem_tema_e_400(cenario: Cenario) -> None:
    """`PATCH` parcial é sobre a **entidade**, não sobre o corpo ser opcional.

    Com um campo só, `{}` não tem leitura útil: ou era um 400 ou era um 200 que
    não faz nada. O 400 é o que diz ao cliente que o pedido estava mal feito, e
    é a forma que não muda no dia em que houver um segundo campo opcional — aí o
    `required` sai deste campo e não desta decisão.
    """
    resposta = _guardar(_cliente(cenario.ana, cenario.alfa.id), {})

    assert resposta.status_code == 400, resposta.content
    assert "tema" in resposta.json()


def test_sem_token_de_csrf_o_patch_e_recusado_e_o_tema_nao_muda(
    cenario: Cenario,
) -> None:
    """A ausência de `csrf_protect` nesta view, medida e não presumida.

    O `as_view()` do DRF embrulha a view em `csrf_exempt`, logo a protecção de
    CSRF desta família **não** vem do middleware: vem do `SessionAuthentication`,
    que verifica o token quando encontra utilizador na sessão. O login e a
    activação levam `csrf_protect` explícito porque são anónimos e esse caminho
    não corre lá (`SECURITY.md` §5) — este não leva, e a diferença é a razão de
    este teste existir.

    As duas metades: sem token é 403 **e a coluna não muda**, com o token que o
    `GET /auth/sessao` devolve é 200.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id, enforce_csrf_checks=True)

    sem_token = _guardar(cliente, {"tema": Tema.CLARO})

    assert sem_token.status_code == 403
    assert _tema_na_base(cenario.ana) == Tema.ESCURO

    cliente.get(URL_SESSAO)
    com_token = _guardar(
        cliente,
        {"tema": Tema.CLARO},
        headers={"x-csrftoken": cliente.cookies[settings.CSRF_COOKIE_NAME].value},
    )

    assert com_token.status_code == 200, com_token.content
    assert _tema_na_base(cenario.ana) == Tema.CLARO


@pytest.mark.parametrize("metodo", ["get", "post", "put", "delete"])
def test_a_rota_so_responde_a_patch(cenario: Cenario, metodo: str) -> None:
    """405 nos outros quatro, e o `GET` é o que interessa dos quatro.

    Não há `GET /auth/preferencias` de propósito: a preferência viaja no
    `GET /auth/sessao` (ADR 0016, decisão 2) e um segundo endpoint a devolvê-la
    era uma segunda fonte para o mesmo valor — o argumento que a ADR 0017 já usou
    para não existir um `GET /menu`.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    resposta = getattr(cliente, metodo)(
        URL_PREFERENCIAS, data={}, content_type="application/json"
    )

    assert resposta.status_code == 405, resposta.content


def test_um_corpo_form_encoded_nao_chega_a_view(cenario: Cenario) -> None:
    """415, pelo `parser_classes = [JSONParser]`.

    A razão é a mesma das views de escrita do `accounts`: um corpo
    `multipart/form-data` é o que um `<form>` de outro domínio consegue enviar
    sem CORS, e recusá-lo no parser fecha essa porta antes de haver view. Aqui
    vale menos do que no login — este pedido é autenticado e o CSRF já o cobre —
    e fica pela mesma razão pela qual a dispensa se pede e não se infere: duas
    camadas a dizer o mesmo não é redundância quando uma delas é a que alguém
    pode mudar sem perceber.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    resposta = cliente.patch(URL_PREFERENCIAS, data={"tema": Tema.CLARO})

    assert resposta.status_code == 415, resposta.content
    assert _tema_na_base(cenario.ana) == Tema.ESCURO
