"""O comando que cria o primeiro estabelecimento e o seu dono (ADR 0010).

Sem este comando não há como entrar na aplicação — não há registo self-service
no v1, por decisão da ADR 0010 — logo o teste que interessa mais não é sobre o
comando: é sobre **entrar**. O `test_depois_do_comando_consegue_se_entrar_pela_api`
corre o comando e faz login pelo endpoint real, que é a única afirmação que
cobre a cadeia inteira (tenant + utilizador + pertença + política + sessão).

Os outros três testes são sobre as três coisas que o comando pode fazer mal e
que ninguém notaria logo: aceitar uma password fraca na conta que abre tudo,
pisar a password de uma conta que já existe, e deixar meio estabelecimento
criado quando a terceira escrita falha.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from apps.accounts import services
from apps.accounts.management.commands.criar_estabelecimento import VARIAVEL_DE_AMBIENTE
from apps.accounts.models import Membership, Papel, User
from apps.shared.db import tenant_scope

URL_LOGIN = "/api/v1/auth/login"

#: A password que o operador escreveria. Passa os `AUTH_PASSWORD_VALIDATORS`:
#: 27 caracteres, não comum, não numérica, e sem semelhança com o email — é o
#: `UserAttributeSimilarityValidator` que faz a última parte importar.
CREDENCIAL_VALIDA = "trigo-fresco-ao-amanhecer-7"

ARGUMENTOS = {
    "nome": "Pastelaria Aurora",
    "email": "ana@aurora.pt",
    "responsavel": "Ana Silva",
    "noinput": True,
}


def _correr(monkeypatch: pytest.MonkeyPatch, password: str, **extra: object) -> str:
    """Corre o comando pelo caminho `--noinput`, com a password no ambiente.

    O caminho interactivo (`getpass`) não é testado de propósito: o que lá vive
    é a confirmação de duas leituras do terminal, e um teste que substitua o
    `getpass` mede o duplo e não o comando. O que **é** testado é que o
    `--noinput` sem a variável de ambiente falha, que é o modo de falha real de
    um script de provisionamento mal configurado.
    """
    monkeypatch.setenv(VARIAVEL_DE_AMBIENTE, password)
    saida = StringIO()
    call_command("criar_estabelecimento", **{**ARGUMENTOS, **extra}, stdout=saida)
    return saida.getvalue()


def test_depois_do_comando_consegue_se_entrar_pela_api(
    transactional_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cadeia inteira, da linha de comandos até à sessão com âmbito.

    É o teste que justifica o comando existir: "sem ele não há como entrar". O
    login é feito pelo endpoint real, logo passa pela descoberta de
    estabelecimentos dentro do `tenant_scope` e pela política — se o
    `conceder_pertenca` tivesse corrido fora do âmbito, o `UPDATE` teria afetado
    zero linhas **sem erro** e este login responderia `sem_estabelecimento`.
    """
    saida = _correr(monkeypatch, CREDENCIAL_VALIDA)

    assert "Estabelecimento criado: Pastelaria Aurora" in saida

    resposta = Client().post(
        URL_LOGIN,
        data={"email": "ana@aurora.pt", "password": CREDENCIAL_VALIDA},
        content_type="application/json",
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["estado"] == "ativa"
    assert corpo["tenant_ativo"]["nome"] == "Pastelaria Aurora"
    assert corpo["tenant_ativo"]["papel"] == Papel.OWNER.value
    # E o uuid impresso é o do estabelecimento ativo: é por ele que o operador
    # identifica o cliente que acabou de criar.
    assert corpo["tenant_ativo"]["id"] in saida


def test_uma_password_fraca_e_recusada(
    transactional_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Os `AUTH_PASSWORD_VALIDATORS` valem também aqui, e é onde mais importa.

    A primeira conta do sistema é a que abre tudo. Um comando que saltasse as
    regras que a API impõe seria a porta mais fraca da casa — e a mais fácil de
    não ver, porque corre uma vez, à mão, no dia da instalação.

    E não deixa nada atrás: a validação corre antes da primeira escrita.

    O `match` é só o número `12` e não a frase: as mensagens dos validadores do
    Django são traduzidas, e a tradução activa num processo de testes não é a do
    `LANGUAGE_CODE` (o `setup_test_environment` desactiva-a). O número é o
    `min_length` do `MinimumLengthValidator` e é o mesmo em qualquer língua —
    logo é ele que identifica o validador que recusou, sem o teste ficar
    dependente da língua.
    """
    with pytest.raises(CommandError, match="12"):
        _correr(monkeypatch, "curta")

    assert not User.objects.filter(email="ana@aurora.pt").exists()


def test_uma_conta_que_ja_existe_nao_muda_de_password(
    transactional_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A regra da ADR 0010, aqui medida pela única prova que conta: o login.

    A password é global e a pertença é por tenant, pelo que "criar um
    estabelecimento e definir a password do dono" daria a quem corre o comando a
    tomada de uma conta existente — com os outros estabelecimentos dela lá
    dentro. O comando concede a pertença e **não** toca na credencial.

    As duas metades são necessárias: que a antiga continue a servir, e que a nova
    não sirva. Com só a primeira, o teste passava se o comando definisse as duas.
    """
    outra = "forno-a-lenha-desde-1987"
    User.objects.create_user("ana@aurora.pt", CREDENCIAL_VALIDA)

    saida = _correr(monkeypatch, outra)

    assert "a password NÃO foi alterada" in saida
    com_a_nova = Client().post(
        URL_LOGIN,
        data={"email": "ana@aurora.pt", "password": outra},
        content_type="application/json",
    )
    assert com_a_nova.status_code == 400

    com_a_antiga = Client().post(
        URL_LOGIN,
        data={"email": "ana@aurora.pt", "password": CREDENCIAL_VALIDA},
        content_type="application/json",
    )
    assert com_a_antiga.status_code == 200
    # E a pertença foi concedida, que é a parte que o comando tinha de fazer.
    assert com_a_antiga.json()["tenant_ativo"]["nome"] == "Pastelaria Aurora"


def test_as_tres_escritas_sao_uma_transacao(
    transactional_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uma falha na pertença não deixa um estabelecimento nem uma conta atrás.

    Sem a transação única, o comando criava o `accounts_tenant` e o
    `accounts_user` e morria na pertença: ficava um estabelecimento inerte
    (invisível, porque sem `Membership` ninguém lhe pode abrir o âmbito) e uma
    conta de email real sem acesso a nada — e a segunda tentativa do operador
    batia no "já existia, a password NÃO foi alterada", com a password que ele
    acabou de escolher a não servir.

    A asserção é sobre o `accounts_user`, que é a tabela **sem** política (ADR
    0007) e portanto a única destas três que se pode ler sem abrir âmbito — o
    que é também o que faz este teste não precisar de saber o uuid que o comando
    gerou e descartou.
    """

    def explode(**kwargs: object) -> Membership:
        raise RuntimeError("a terceira escrita falhou")

    monkeypatch.setattr(services, "conceder_pertenca", explode)

    with pytest.raises(RuntimeError, match="terceira escrita"):
        _correr(monkeypatch, CREDENCIAL_VALIDA)

    assert not User.objects.filter(email="ana@aurora.pt").exists()


def test_o_noinput_sem_a_variavel_de_ambiente_falha(
    transactional_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E a mensagem diz porque é que não há um `--password`.

    Um argumento de linha de comandos fica no histórico da shell e aparece no
    `ps` de qualquer utilizador da máquina. Vale dizê-lo na mensagem de erro:
    quem está a escrever um script de provisionamento é exactamente quem vai
    procurar esse argumento.
    """
    monkeypatch.delenv(VARIAVEL_DE_AMBIENTE, raising=False)

    with pytest.raises(CommandError, match="histórico da shell"):
        call_command("criar_estabelecimento", **ARGUMENTOS)


def test_o_display_name_vive_no_membership_e_nao_no_user(
    transactional_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O `--responsavel` escreve no `Membership`, que é a tabela com política.

    A mesma pessoa é "Ana Silva (contabilidade)" num estabelecimento e "Ana"
    noutro (ADR 0007), e o `accounts_user` não tem política — um nome lá seria
    perfil legível por qualquer ligação da app. É por isso que o comando pede o
    nome do responsável em vez de o derivar do email.
    """
    _correr(monkeypatch, CREDENCIAL_VALIDA)
    user = User.objects.get(email="ana@aurora.pt")

    assert len(user.tenant_ids) == 1
    with tenant_scope(user.tenant_ids[0]):
        pertenca = Membership.objects.get(user=user)
        assert pertenca.display_name == "Ana Silva"
        assert pertenca.role == Papel.OWNER.value
        assert pertenca.tenant.name == "Pastelaria Aurora"
