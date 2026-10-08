"""Smoke tests da camada de configuração.

Não testam regras de negócio: testam que os quatro módulos de settings
importam, que os defaults perigosos ficam desligados e que o formatter de logs
não deixa passar campos fora da allowlist.

Nenhum destes testes toca na base de dados. O ambiente vem do `clean_env` do
`conftest.py` — nunca do shell de quem corre a suite.
"""

from __future__ import annotations

import copy
import json
import logging
import pathlib
import re
import sys

import pytest
from django.conf import settings

from config.log import JsonFormatter, RequestContextFilter
from tests.conftest import reload_settings as _reload


def test_base_e_dev_importam(clean_env: None) -> None:
    base = _reload("base")
    dev = _reload("dev")

    assert base.DEBUG is False, "o default do base tem de ser fechado"
    assert base.ALLOWED_HOSTS == []
    assert dev.DEBUG is True
    assert dev.SECURE_SSL_REDIRECT is False
    assert dev.SECURE_HSTS_SECONDS == 0
    # Portas do ADR 0002: proxy, API e Vite.
    assert "http://localhost:8090" in dev.CSRF_TRUSTED_ORIGINS
    assert "http://localhost:8010" in dev.CSRF_TRUSTED_ORIGINS
    assert "http://localhost:5183" in dev.CSRF_TRUSTED_ORIGINS


def test_debug_desligado_em_test_e_prod(prod_env: None) -> None:
    assert settings.DEBUG is False, "as settings ativas na suite são as de teste"
    assert _reload("test").DEBUG is False
    assert _reload("prod").DEBUG is False


def test_prod_traz_o_bloco_de_seguranca(prod_env: None) -> None:
    prod = _reload("prod")

    assert prod.SECURE_SSL_REDIRECT is True
    assert prod.SECURE_HSTS_SECONDS == 31536000
    assert prod.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
    assert prod.SECURE_HSTS_PRELOAD is True
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.CSRF_COOKIE_SECURE is True
    assert prod.X_FRAME_OPTIONS == "DENY"
    # TLS verificado na ligação à BD (SECURITY.md §3).
    assert prod.DATABASES["default"]["OPTIONS"]["sslmode"] == "verify-full"


def test_prod_nao_muta_os_dicionarios_do_base(prod_env: None) -> None:
    """O `import *` traz a *referência* dos dicionários do `base`.

    Se o `prod.py` mutasse um deles em vez de construir um novo, a configuração
    de quem importasse o `base` noutro ambiente mudava com ele — e em produção
    isso é uma setting de segurança a aparecer onde não devia (ou a
    desaparecer). Este teste existe para travar essa mutação.

    Nota sobre o que **não** se pode assertar aqui: `django.conf.settings`
    guarda os objetos que o `config.settings.test` ligou no arranque da suite, e
    um `_reload("base")` cria dicionários novos. Depois do primeiro reload,
    `settings.DATABASES` é um objeto órfão, sem relação com o que o `prod.py`
    acabou de ler: uma asserção sobre ele passa aconteça o que acontecer no
    `prod.py`. O peso está em comparar o módulo `base` consigo mesmo, antes e
    depois de o `prod` ser lido.
    """
    base = _reload("base")
    antes = copy.deepcopy(
        {
            "DATABASES": base.DATABASES,
            "CONTENT_SECURITY_POLICY": base.CONTENT_SECURITY_POLICY,
            "REST_FRAMEWORK": base.REST_FRAMEWORK,
        }
    )

    prod = _reload("prod")

    # O prod mudou mesmo alguma coisa (senão o teste passava por vacuidade).
    assert prod.DATABASES["default"]["OPTIONS"]["sslmode"] == "verify-full"
    assert prod.CONTENT_SECURITY_POLICY["DIRECTIVES"]["upgrade-insecure-requests"] is True
    assert prod.REST_FRAMEWORK["NUM_PROXIES"] == 1

    # E o base ficou exatamente como estava.
    assert base.DATABASES == antes["DATABASES"]
    assert base.CONTENT_SECURITY_POLICY == antes["CONTENT_SECURITY_POLICY"]
    assert base.REST_FRAMEWORK == antes["REST_FRAMEWORK"]
    assert "sslmode" not in base.DATABASES["default"].get("OPTIONS", {})

    # Objetos distintos até ao nível que o prod toca: é isto que impede uma
    # mutação futura de se propagar.
    assert prod.DATABASES is not base.DATABASES
    assert prod.DATABASES["default"] is not base.DATABASES["default"]
    assert prod.CONTENT_SECURITY_POLICY is not base.CONTENT_SECURITY_POLICY
    assert prod.REST_FRAMEWORK is not base.REST_FRAMEWORK


def test_argon2_a_frente_e_minimo_de_12_chars(prod_env: None) -> None:
    argon2 = "django.contrib.auth.hashers.Argon2PasswordHasher"
    assert _reload("base").PASSWORD_HASHERS[0] == argon2
    assert _reload("prod").PASSWORD_HASHERS[0] == argon2
    # A suite corre com MD5 por velocidade, e é o único sítio onde isso vale
    # (ver o comentário em `config/settings/test.py`).
    assert settings.PASSWORD_HASHERS == ["django.contrib.auth.hashers.MD5PasswordHasher"]

    minimo = [
        validator
        for validator in settings.AUTH_PASSWORD_VALIDATORS
        if validator["NAME"].endswith("MinimumLengthValidator")
    ]
    assert minimo[0]["OPTIONS"]["min_length"] == 12


def test_sessao_expira_com_14_dias_de_inatividade() -> None:
    assert settings.SESSION_COOKIE_AGE == 14 * 24 * 60 * 60
    # Sem isto os 14 dias contariam desde o login, não desde o último pedido.
    assert settings.SESSION_SAVE_EVERY_REQUEST is True
    assert settings.SESSION_COOKIE_HTTPONLY is True


def test_csp_sem_unsafe_inline_e_sem_frames() -> None:
    directives = settings.CONTENT_SECURITY_POLICY["DIRECTIVES"]

    assert directives["default-src"] == ["'self'"]
    assert directives["frame-ancestors"] == ["'none'"]
    assert all("unsafe-inline" not in str(value) for value in directives.values())


def _record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="apps.inventory",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="movimento registado",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_descarta_extra_fora_da_allowlist() -> None:
    record = _record(event="stock.movement.recorded", nif="123456789", email="a@b.pt")

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "movimento registado"
    assert payload["event"] == "stock.movement.recorded"
    # PII fora da allowlist não chega ao output — falha fechada.
    assert "nif" not in payload
    assert "email" not in payload


def test_request_context_filter_garante_os_campos_de_correlacao() -> None:
    record = _record()

    assert RequestContextFilter().filter(record) is True

    payload = json.loads(JsonFormatter().format(record))
    assert payload["request_id"] is None
    assert payload["tenant_id"] is None
    assert payload["user_id"] is None


# ---------------------------------------------------------------------------
# Onde a allowlist do `config/log.py` acaba. Os dois testes seguintes afirmam
# que os `%`-args e o traceback **passam em claro** — não é o comportamento
# desejável, é o comportamento real, e fica fixado em código para a convenção
# do docstring do `config/log.py` (PII só em `extra=`) não se perder em prosa.
# Se um dia houver um scrubber, estes dois testes é que mudam de sinal.
# ---------------------------------------------------------------------------
def test_allowlist_nao_cobre_a_mensagem_nem_os_percent_args() -> None:
    record = logging.LogRecord(
        name="apps.purchasing",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="fatura de %s para o NIF %s",
        args=("cliente@exemplo.pt", "123456789"),
        exc_info=None,
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "fatura de cliente@exemplo.pt para o NIF 123456789"


def test_allowlist_nao_cobre_o_traceback_da_excecao() -> None:
    try:
        raise ValueError("DETAIL: Key (nif)=(123456789) already exists.")
    except ValueError:
        record = logging.LogRecord(
            name="apps.purchasing",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="falha ao gravar o fornecedor",
            args=(),
            exc_info=sys.exc_info(),
        )

    payload = json.loads(JsonFormatter().format(record))

    assert "123456789" in payload["exception"]


@pytest.mark.parametrize(
    ("modulo", "esperado"),
    [("base", 0), ("dev", 0), ("test", 0), ("prod", 1)],
)
def test_num_proxies_definido_em_todos_os_ambientes(
    prod_env: None, modulo: str, esperado: int
) -> None:
    """Sem `NUM_PROXIES` o DRF usa o `X-Forwarded-For` cru como identidade.

    `BaseThrottle.get_ident` só ignora o header quando a setting existe: a
    `None` devolve o header todo concatenado, e o limite de `60/min` para
    anónimos contorna-se a rodar um valor qualquer no header. `0` = usa só o
    `REMOTE_ADDR`; em prod é o nº de proxies de confiança.
    """
    assert _reload(modulo).REST_FRAMEWORK["NUM_PROXIES"] == esperado


# ---------------------------------------------------------------------------
# Email (SMTP) em produção
# ---------------------------------------------------------------------------
def test_prod_nunca_cai_na_consola_mesmo_sem_smtp_configurado(
    prod_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Um email "enviado" para o stdout de um contentor é a pior falha possível.

    Não levanta, não aparece em log nenhum, e a pessoa do outro lado fica à espera
    de uma mensagem que nunca existiu. **Esta é a metade da decisão que fica**: o
    backend é SMTP e não há variável, default ou caminho que o troque pela consola.

    A outra metade saiu a 2026-10-08. O `EMAIL_HOST` era `required` sem default, e
    com nada neste código a enviar email isso só comprava um valor de fachada para
    o deploy passar — que **parece** configurado e falha mais tarde com menos
    contexto. Já partiu a build das imagens uma vez, porque o `collectstatic`
    importa este ficheiro.

    Então o teste afirma agora o contrário do que afirmava: **sem `EMAIL_HOST` o
    módulo importa**, e o backend continua a ser o de SMTP. Quem garante que isto
    não fica assim para sempre é o
    `test_o_smtp_volta_a_ser_obrigatorio_quando_alguem_enviar`, que varre as apps
    à procura de um remetente.
    """
    prod = _reload("prod")

    assert prod.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend"
    assert prod.EMAIL_HOST == "smtp.example.pt"
    assert prod.DEFAULT_FROM_EMAIL == "StockFlow <stockflow@example.pt>"

    monkeypatch.delenv("EMAIL_HOST")
    monkeypatch.delenv("DEFAULT_FROM_EMAIL")
    sem_smtp = _reload("prod")

    assert sem_smtp.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend", (
        "sem SMTP configurado o backend mudou — é o único caminho que não pode "
        "existir, porque um email no stdout não levanta e não aparece em log nenhum."
    )
    assert sem_smtp.EMAIL_HOST == ""
    assert sem_smtp.DEFAULT_FROM_EMAIL == "", (
        "o default do Django é `webmaster@localhost`, um endereço que não existe em "
        "domínio nenhum: a mensagem sai, quem recebe rejeita-a por SPF, e o envio "
        "'funciona' sem ninguém receber. Vazio não finge nada."
    )


@pytest.mark.parametrize(
    ("porta", "ssl", "tls"),
    [(587, False, True), (465, True, False), (25, False, True), (2525, False, True)],
)
def test_o_tls_do_smtp_e_derivado_da_porta_e_nunca_os_dois(
    prod_env: None, monkeypatch: pytest.MonkeyPatch, porta: int, ssl: bool, tls: bool
) -> None:
    """`EMAIL_USE_SSL` e `EMAIL_USE_TLS` são mutuamente exclusivos no Django.

    Ligar os dois faz o `smtplib` falhar com uma mensagem que não aponta para
    isto, e deixar os dois desligados manda a password de SMTP em claro na rede.
    Daí serem **derivados da porta** em vez de duas variáveis: não há forma de
    discordarem, e não há caminho para desligar os dois.

    A porta 465 é TLS implícito (liga já cifrado) e tudo o resto é STARTTLS
    (liga em claro e promove) — incluindo a 25 e as portas alternativas que
    alguns serviços usam, que é o caso de `2525` estar aqui.
    """
    monkeypatch.setenv("EMAIL_PORT", str(porta))

    prod = _reload("prod")

    assert prod.EMAIL_PORT == porta
    assert prod.EMAIL_USE_SSL is ssl
    assert prod.EMAIL_USE_TLS is tls
    assert prod.EMAIL_USE_SSL != prod.EMAIL_USE_TLS, (
        "os dois não podem estar ligados nem desligados ao mesmo tempo"
    )


def test_o_dev_escreve_na_consola_e_o_test_guarda_em_memoria(clean_env: None) -> None:
    """E é por isso que nada disto é preciso para desenvolver.

    Vale um teste porque é a razão pela qual o `prod.py` **pode** ser
    intransigente: quem desenvolve nunca precisa de um SMTP, logo exigir um em
    produção não custa nada a ninguém que esteja a trabalhar.
    """
    assert (
        _reload("dev").EMAIL_BACKEND
        == "django.core.mail.backends.console.EmailBackend"
    )
    assert (
        _reload("test").EMAIL_BACKEND
        == "django.core.mail.backends.locmem.EmailBackend"
    )


# ---------------------------------------------------------------------------
# A fachada do `collectstatic` tem de acompanhar o `prod.py`
# ---------------------------------------------------------------------------

#: O `prod.py` e a linha do `collectstatic` do Dockerfile, lidos como texto.
RAIZ = pathlib.Path(__file__).resolve().parents[2]
PROD = RAIZ / "backend/config/settings/prod.py"
DOCKERFILE = RAIZ / "docker/backend.Dockerfile"


def test_a_fachada_do_collectstatic_cobre_todos_os_required_do_prod() -> None:
    """O `collectstatic` da build importa o `prod.py`, e é o único sítio que o faz.

    **Esta é a divergência que já aconteceu**, a 2026-10-07: o commit que tornou
    o SMTP obrigatório acrescentou quatro `required(env, …)` ao `prod.py` e não
    tocou na linha do Dockerfile. Nada local o disse — o `pytest` usa
    `settings.test`, o `manage.py` usa `settings.dev` — e o sintoma foi um
    `KeyError: 'EMAIL_HOST'` a partir a build de imagens no CI, dezoito commits
    depois de a causa ter entrado.

    Este teste é a única coisa que liga as duas pontas, e **é texto a ler texto**
    de propósito: importar o `prod.py` aqui obrigava a ter a fachada no ambiente
    do teste, que é precisamente o acoplamento que se quer medir em vez de
    satisfazer.

    O que afirma é a inclusão, e não a igualdade: a fachada pode trazer mais do
    que o `prod.py` exige (o `EMAIL_PORT`, por exemplo, tem default).
    """
    exigidas = set(re.findall(r'required\(\s*env\s*,\s*"([A-Z0-9_]+)"', PROD.read_text()))
    assert exigidas, (
        f"não encontrei nenhum `required(env, …)` em {PROD}. Se a forma mudou, este "
        "teste deixou de medir o que diz medir — arranja-o em vez de o apagar."
    )

    dockerfile = DOCKERFILE.read_text()
    # O fecho é `python manage.py collectstatic` e não `collectstatic`: a própria
    # linha gera a chave com um `x-collectstatic-…`, e um `.*?collectstatic`
    # fechava ali — o teste passava a ler uma fachada de uma variável só. Apanhado
    # porque ele acusou seis que **estavam** lá.
    bloco = re.search(
        r"RUN DJANGO_SECRET_KEY=.*?python manage\.py collectstatic", dockerfile, re.DOTALL
    )
    assert bloco is not None, f"não encontrei a linha do `collectstatic` em {DOCKERFILE}"
    na_fachada = set(re.findall(r"([A-Z0-9_]+)=", bloco.group(0)))

    assert exigidas <= na_fachada, (
        "o `prod.py` passou a exigir variáveis que a fachada do `collectstatic` não "
        f"dá: {sorted(exigidas - na_fachada)}. Acrescenta-as à linha `RUN` do "
        f"{DOCKERFILE.name} — senão a build da imagem falha com um `KeyError`, e só "
        "no CI, porque é o único sítio onde o `prod.py` é importado."
    )


#: Os nomes que o Django usa para enviar email. Se um deles aparecer nas apps,
#: há um remetente — e a configuração de SMTP deixa de poder ser opcional.
#:
#: `mail_admins` fica de fora de propósito: é o único consumidor que o Django traz
#: de série, só envia com `ADMINS` configurado, e o `prod.py` diz por extenso que
#: não está.
REMETENTES = (
    "send_mail(",
    "send_mass_mail(",
    "EmailMessage(",
    "EmailMultiAlternatives(",
    ".send_messages(",
)


def test_o_smtp_volta_a_ser_obrigatorio_quando_alguem_enviar() -> None:
    """A condição que torna o SMTP opcional, verificada em vez de prometida.

    O `prod.py` tinha as quatro variáveis de email **obrigatórias sem default**,
    pelo argumento certo — um default que caia na consola era um email "enviado"
    para o stdout de um contentor. Mas nada neste código envia email: o convite é
    entregue à mão por desenho (ADR 0010) e a reposição de password não existe.
    Exigir SMTP para arrancar um produto que não envia nada compra uma coisa só:
    um valor de fachada, que **parece** configurado e falha mais tarde com menos
    contexto. Já partiu a build das imagens uma vez.

    Então ficaram opcionais — e este teste é o que impede isso de se tornar
    permanente por esquecimento. No dia em que alguém escrever o primeiro
    remetente, ele fica vermelho e a mensagem diz o que fazer: um deploy sem
    servidor de email tem de falhar no **arranque** e não no envio.

    Varre o código das apps e não o `.venv`: o Django envia emails lá dentro (o
    reset de password dele, o `mail_admins`) e isso não é um remetente nosso.
    """
    apps = pathlib.Path(__file__).resolve().parents[1] / "apps"
    com_remetente: list[str] = []
    for ficheiro in sorted(apps.rglob("*.py")):
        if "/migrations/" in ficheiro.as_posix():
            continue
        fonte = ficheiro.read_text(encoding="utf-8")
        # Sem comentários: este repositório fala sobre email em prosa mais vezes
        # do que o enviaria, e um gate que acusa quem documenta ensina a não
        # documentar — é a lição que o `security_check.sh` aprendeu duas vezes.
        fonte = re.sub(r'"""[\s\S]*?"""', "", fonte)
        fonte = re.sub(r"^\s*#.*$", "", fonte, flags=re.MULTILINE)
        if any(nome in fonte for nome in REMETENTES):
            com_remetente.append(ficheiro.relative_to(apps).as_posix())

    obrigatorio = 'required(env, "EMAIL_HOST")' in PROD.read_text(encoding="utf-8")

    assert bool(com_remetente) == obrigatorio, (
        f"remetentes de email encontrados: {com_remetente or 'nenhum'}; "
        f"`EMAIL_HOST` obrigatório no prod.py: {obrigatorio}. "
        "Com um remetente, as quatro variáveis de SMTP voltam a `required(env, …)` "
        "— e acrescenta-as à fachada do `collectstatic` no Dockerfile, senão a "
        "build das imagens parte (já partiu). Sem remetente nenhum, exigir SMTP só "
        "compra um valor de fachada que finge estar configurado."
    )
