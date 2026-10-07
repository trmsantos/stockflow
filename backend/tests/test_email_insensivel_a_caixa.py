"""A caixa do email não distingue contas — nos quatro sítios onde isso se decide.

`Ana@x.pt` e `ana@x.pt` são a **mesma** conta. Isso não é uma propriedade de um
sítio só: é uma regra que tem de valer ao mesmo tempo na base de dados, na
escrita, no lookup da autenticação e no contador de tentativas do axes. Falhar
uma delas dá um defeito diferente e nenhum é benigno:

| Onde falha | O que acontece |
|---|---|
| Índice único | duas linhas casam o lookup: `MultipleObjectsReturned`, login a 500 |
| `normalize_email` | a linha fica fora da forma canónica |
| `get_by_natural_key` | registo com `ana@` e login com `Ana@` dá credenciais inválidas |
| `AXES_USERNAME_CALLABLE` | o contador de falhas fragmenta-se e o lockout não tranca |

A primeira linha é a que explica porque é que o índice e o lookup têm de entrar
**juntos**: um lookup insensível à caixa sobre uma coluna que permite duas
grafias encontra duas linhas, e aí já não é um erro de credenciais, é um 500.

Por isso os testes estão todos neste ficheiro e não repartidos: o que se prova
não é uma função, é a coerência entre as quatro.

O `accounts_user` é a tabela **sem** política de RLS (ADR 0007), pelo que tudo
aqui corre fora de âmbito de tenant — e é assim que tem de ser: o login lê esta
tabela antes de existir âmbito nenhum. O guarda do `conftest.py` não a cobre, de
propósito.
"""

from __future__ import annotations

import pytest
from asgiref.sync import async_to_sync
from axes.handlers.proxy import AxesProxyHandler
from axes.helpers import get_client_username
from axes.models import AccessAttempt
from django.conf import settings
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.http import HttpRequest
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext

from apps.accounts.api import normalizar_email
from apps.accounts.models import User

#: A conta do cenário, e as grafias com que se tenta chegar a ela.
EMAIL = "ana@exemplo.pt"
#: Uma segunda conta, para provar que os contadores não se somam entre contas.
EMAIL_OUTRO = "bruno@exemplo.pt"
EMAIL_CAIXA_ALTA = "ANA@EXEMPLO.PT"
EMAIL_CAIXA_MISTA = "Ana@Exemplo.pt"

#: Os nomes não dizem "password" de propósito: o S105 do ruff (flake8-bandit)
#: acusa qualquer constante com esse nome, e neste repositório não se suprime
#: uma regra de lint (CLAUDE.md).
CREDENCIAL_CERTA = "palavra-de-teste-1234"
CREDENCIAL_ERRADA = "nao-confere-1234"

URL_LOGIN = "/api/v1/auth/login/"


@pytest.fixture
def ana(db: None) -> User:
    """A conta criada pelo caminho normal: o manager."""
    return User.objects.create_user(EMAIL, CREDENCIAL_CERTA)


def _pedido(email: str) -> HttpRequest:
    """Um POST de login com esta grafia no corpo, como o cliente o manda."""
    return RequestFactory().post(URL_LOGIN, {"email": email})


# ---------------------------------------------------------------------------
# 1. A normalização na escrita
# ---------------------------------------------------------------------------
def test_o_manager_guarda_o_email_na_forma_canonica(db: None) -> None:
    """Tudo em minúsculas, parte local incluída.

    O `normalize_email` do Django dobra só o domínio; a sobreposição do
    `UserManager` dobra a parte local também, porque é o que faz par com o
    índice sobre `LOWER(email)`.
    """
    user = User.objects.create_user(EMAIL_CAIXA_MISTA, CREDENCIAL_CERTA)

    assert user.email == EMAIL
    assert User.objects.get(pk=user.pk).email == EMAIL


def test_o_create_superuser_passa_pelo_mesmo_caminho(db: None) -> None:
    """Um operador do StockFlow não é um caso especial.

    `create_superuser` delega em `create_user` de propósito: dois caminhos de
    criação com duas normalizações diferentes davam um superuser fora da forma
    canónica, e a conta que o `createsuperuser` cria é precisamente a que
    ninguém volta a olhar.
    """
    operador = User.objects.create_superuser(EMAIL_CAIXA_ALTA, CREDENCIAL_CERTA)

    assert operador.email == EMAIL
    assert operador.is_staff and operador.is_superuser


def test_normalizar_email_e_a_porta_publica_da_mesma_regra() -> None:
    """O que o `accounts.api` exporta é a definição de "a mesma conta"."""
    assert normalizar_email(EMAIL_CAIXA_MISTA) == EMAIL
    assert normalizar_email(EMAIL_CAIXA_ALTA) == EMAIL
    assert normalizar_email(EMAIL) == EMAIL
    # Sem valor não levanta: quem valida a forma é o campo, não esta função.
    assert normalizar_email(None) == ""


# ---------------------------------------------------------------------------
# 2. O índice único, que é a rede por baixo da normalização
# ---------------------------------------------------------------------------
def test_criar_a_mesma_conta_com_outra_caixa_e_recusado(ana: User) -> None:
    """O caminho normal: o manager normaliza e a unicidade recusa a segunda."""
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(EMAIL_CAIXA_MISTA, CREDENCIAL_CERTA)

    assert User.objects.count() == 1


def test_a_constraint_recusa_mesmo_quem_nao_passa_pelo_manager(ana: User) -> None:
    """A regra está na base de dados, não só no código (SECURITY.md §1).

    Aqui escreve-se por baixo do manager — `User(...).save()`, que é o que um
    `loaddata`, uma migração de dados ou um `save()` distraído fazem — e a
    linha não entra. O nome no erro é o do índice funcional, e é a prova de que
    foi ele a recusar: o `accounts_user_email_key` compara o email byte a byte e
    deixaria `Ana@Exemplo.pt` passar.
    """
    with pytest.raises(IntegrityError, match="user_email_lower_uniq"), transaction.atomic():
        User(email=EMAIL_CAIXA_MISTA).save()

    assert User.objects.count() == 1


def test_o_formulario_do_admin_dobra_a_caixa_e_recusa_o_duplicado(ana: User) -> None:
    """O `full_clean()`, que é o caminho do único formulário que edita emails.

    O admin registra o `User` e o seu `ModelForm` escreve pelo `save()` do
    modelo, não pelo manager. O gancho que lá dobra a caixa é o
    `User.normalize_username`, que o `AbstractBaseUser.clean()` chama — e a
    seguir a validação de unicidade vê o duplicado e devolve um erro de
    formulário em vez de um `IntegrityError` a subir da base de dados.
    """
    outra = User(email=EMAIL_CAIXA_ALTA)
    outra.set_password(CREDENCIAL_CERTA)

    with pytest.raises(ValidationError) as erro:
        outra.full_clean()

    assert outra.email == EMAIL, "o clean() tem de normalizar antes de validar"
    assert "email" in erro.value.message_dict


# ---------------------------------------------------------------------------
# 3. O lookup da autenticação
# ---------------------------------------------------------------------------
def test_autenticar_com_a_caixa_trocada_funciona(ana: User) -> None:
    """A metade que faltaria para isto ser o pior dos dois mundos.

    Sem um lookup insensível à caixa, registar `ana@` e tentar entrar com `Ana@`
    dava "credenciais inválidas" numa conta que existe — e a unicidade sem caixa
    garantia que não havia outra conta para onde ir.
    """
    assert authenticate(request=None, email=EMAIL_CAIXA_ALTA, password=CREDENCIAL_CERTA) == ana
    assert authenticate(request=None, email=EMAIL_CAIXA_MISTA, password=CREDENCIAL_CERTA) == ana
    # E pela outra forma de chamar o `authenticate()`, que é a do admin.
    assert authenticate(request=None, username=EMAIL_CAIXA_ALTA, password=CREDENCIAL_CERTA) == ana


def test_a_password_continua_a_ser_verificada(ana: User) -> None:
    """A guarda óbvia: dobrar a caixa do email não dobra mais nada."""
    assert authenticate(request=None, email=EMAIL, password=CREDENCIAL_ERRADA) is None
    assert authenticate(request=None, email="outra@exemplo.pt", password=CREDENCIAL_CERTA) is None


def test_o_get_by_natural_key_procura_pela_expressao_do_indice(ana: User) -> None:
    """`LOWER(email) = %s`, que é exatamente o predicado do índice único.

    Não é cosmética: um `email__iexact` gerava
    `UPPER(email::text) LIKE UPPER(%s)`, que o índice funcional não cobre — o
    login passava a varrer a tabela de utilizadores toda. E comparar
    `email = <valor normalizado>` encontrava só as linhas já canónicas, o que
    deixava de fora uma linha escrita por um caminho que não normalizou.
    """
    with CaptureQueriesContext(connection) as queries:
        assert User.objects.get_by_natural_key(EMAIL_CAIXA_ALTA) == ana

    sql = queries.captured_queries[-1]["sql"]
    assert "LOWER" in sql.upper()

    with pytest.raises(User.DoesNotExist):
        User.objects.get_by_natural_key("ninguem@exemplo.pt")


def test_a_versao_assincrona_do_lookup_segue_a_mesma_regra(ana: User) -> None:
    """Uma segunda definição de "o mesmo email" entraria por aqui.

    O `ModelBackend.aauthenticate` usa `aget_by_natural_key`. Sem a sobreposição
    o caminho assíncrono caía no do Django, sensível à caixa, e a incoerência só
    aparecia no dia da primeira view `async`.
    """
    encontrada = async_to_sync(User.objects.aget_by_natural_key)(EMAIL_CAIXA_MISTA)

    assert encontrada == ana


# ---------------------------------------------------------------------------
# 4. O contador de tentativas do axes
#
# O axes não normaliza nada (ver `config/lockout.py`): escreve e lê o
# `AccessAttempt.username` com o valor cru do pedido. Os dois testes seguintes
# são um par — o primeiro afirma que hoje o contador não se fragmenta, o segundo
# que é o `AXES_USERNAME_CALLABLE` que o impede. Sem o segundo, o primeiro
# passava com a setting apagada.
# ---------------------------------------------------------------------------
def _falhar_login(email: str) -> None:
    """Uma tentativa de login falhada com esta grafia, pelo caminho real.

    `authenticate()` emite o sinal `user_login_failed` com as credenciais tal
    como o chamador as passou, e é o handler do axes que escreve a linha.
    """
    assert authenticate(request=_pedido(email), email=email, password=CREDENCIAL_ERRADA) is None


@override_settings(AXES_ENABLED=True)
def test_o_contador_do_axes_nao_se_fragmenta_com_a_caixa(ana: User) -> None:
    """Três tentativas com `ana@` e duas com `Ana@` são cinco na mesma conta.

    É o caso que o lockout precisa de apanhar: sem normalização, quem variasse a
    caixa entre tentativas tinha tentativas ilimitadas de graça — cada grafia
    era uma linha própria e o `max()` do `get_failures` nunca chegava ao limite.
    """
    for _ in range(3):
        _falhar_login(EMAIL)
    for _ in range(2):
        _falhar_login(EMAIL_CAIXA_MISTA)

    tentativas = list(AccessAttempt.objects.values_list("username", "failures_since_start"))

    assert tentativas == [(EMAIL, 5)], "as cinco falhas têm de ir para a mesma linha"
    assert AxesProxyHandler.get_failures(_pedido(EMAIL_CAIXA_ALTA)) == settings.AXES_FAILURE_LIMIT
    # E a conta fica trancada para qualquer grafia, que é o ponto de tudo isto.
    assert AxesProxyHandler.is_locked(_pedido(EMAIL_CAIXA_ALTA)) is True
    assert AxesProxyHandler.is_locked(_pedido(EMAIL)) is True


@override_settings(AXES_ENABLED=True, AXES_USERNAME_CALLABLE=None)
def test_sem_o_callable_o_contador_fragmenta_se_e_ninguem_tranca(ana: User) -> None:
    """A outra metade: é o `AXES_USERNAME_CALLABLE` que faz o trabalho.

    Com ele apagado, o axes volta ao valor cru do formulário: duas linhas, de
    três e de duas falhas, o `get_failures` devolve 3 e as cinco tentativas não
    trancam nada. É isto que estava a acontecer.
    """
    for _ in range(3):
        _falhar_login(EMAIL)
    for _ in range(2):
        _falhar_login(EMAIL_CAIXA_MISTA)

    tentativas = dict(AccessAttempt.objects.values_list("username", "failures_since_start"))

    assert tentativas == {EMAIL: 3, EMAIL_CAIXA_MISTA: 2}
    assert AxesProxyHandler.get_failures(_pedido(EMAIL)) == 3
    assert AxesProxyHandler.is_locked(_pedido(EMAIL)) is False


def test_o_callable_acha_a_conta_nas_duas_formas_de_chamar_o_authenticate() -> None:
    """E normaliza-a nas duas. Sem base de dados: é resolução de nome, não query.

    O `authenticate()` do Django emite o sinal com os kwargs que recebeu, pelo
    que as credenciais que chegam ao axes trazem a conta na chave `email` (a
    nossa API) ou na chave `username` (o `AuthenticationForm` do admin e a forma
    canónica do `authenticate()`). O axes procura só a primeira e, se o
    dicionário não estiver vazio, não desce ao corpo do pedido: o caminho do
    admin ficava todo registado com `username = NULL`, que é um contador global
    e não um contador por conta.
    """
    pedido = _pedido(EMAIL_CAIXA_MISTA)

    assert get_client_username(pedido) == EMAIL
    assert get_client_username(pedido, {"email": EMAIL_CAIXA_ALTA, "password": "***"}) == EMAIL
    assert get_client_username(pedido, {"username": EMAIL_CAIXA_ALTA, "password": "***"}) == EMAIL


def test_um_pedido_sem_o_campo_da_conta_nao_inventa_uma() -> None:
    """`None`, como no axes: não identifica conta nenhuma.

    A segunda asserção é a que protege o login de um corpo JSON hostil: um valor
    que não é texto chegaria ao `filter(username=[...])` do axes e rebentava a
    query — aqui cai no mesmo sítio que a ausência do campo.
    """
    assert get_client_username(RequestFactory().post(URL_LOGIN, {})) is None
    assert get_client_username(RequestFactory().post(URL_LOGIN), {"email": ["a", "b"]}) is None


# ---------------------------------------------------------------------------
# 5. O caminho do admin, que é o que o teste acima não consegue distinguir
# ---------------------------------------------------------------------------
def test_o_caminho_do_admin_nao_tem_o_nosso_campo_em_sitio_nenhum() -> None:
    """Nem nas credenciais nem no corpo há `email` — e é esse o caso real.

    O teste da precedência, acima, constrói o pedido com `_pedido()`, que põe
    `{"email": ...}` no **corpo**. Com isso, o valor é encontrado no corpo e a
    asserção passa com ou sem a procura da chave `username` nas credenciais: o
    pedido não distingue as duas implementações, e a lacuna que ele diz cobrir
    fica escondida.

    No `AuthenticationForm` do admin o campo chama-se `username`, e é isso que
    vai no corpo *e* nas credenciais — `email` não existe em lado nenhum. Se só
    se procurar a nossa chave, o resultado é `None`; e um `None` no eixo
    `"username"` do `AXES_LOCKOUT_PARAMETERS` não é um contador a menos, é um
    contador **global**: casa `filter(username=None)`, que são as tentativas de
    todas as contas juntas.
    """
    pedido = RequestFactory().post("/gestao-interna/login/", {"username": EMAIL_CAIXA_MISTA})

    assert get_client_username(pedido) == EMAIL
    assert get_client_username(pedido, {"username": EMAIL_CAIXA_ALTA, "password": "***"}) == EMAIL


@override_settings(AXES_ENABLED=True)
def test_falhas_de_contas_diferentes_pelo_caminho_do_admin_nao_se_somam(db: None) -> None:
    """A consequência, medida: três falhas de uma conta e duas de outra.

    Pelo caminho canónico do `authenticate(request, username=..., password=...)`,
    que é o do admin. Sem a segunda chave, as cinco linhas colapsavam numa só
    com `username = NULL` e o limite de cinco falhas trancava **as duas** contas
    — cinco pessoas diferentes a errar a password trancavam o login a todas.
    """
    User.objects.create_user(EMAIL, CREDENCIAL_CERTA)
    User.objects.create_user(EMAIL_OUTRO, CREDENCIAL_CERTA)

    for conta, vezes in ((EMAIL, 3), (EMAIL_OUTRO, 2)):
        for _ in range(vezes):
            pedido = RequestFactory().post("/gestao-interna/login/", {"username": conta})
            assert authenticate(request=pedido, username=conta, password=CREDENCIAL_ERRADA) is None

    contagem = dict(AccessAttempt.objects.values_list("username", "failures_since_start"))

    assert contagem == {EMAIL: 3, EMAIL_OUTRO: 2}, "cada conta tem o seu contador"
    assert None not in contagem, "uma linha com username NULL é um contador global"
    # E nenhuma das duas tranca: 3 e 2 estão abaixo do limite de 5. Se os
    # contadores se somassem, as duas estariam trancadas aqui.
    for conta in (EMAIL, EMAIL_OUTRO):
        pedido = RequestFactory().post("/gestao-interna/login/", {"username": conta})
        assert AxesProxyHandler.is_locked(pedido) is False
