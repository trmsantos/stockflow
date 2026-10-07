"""O português é o de Portugal, e o mecanismo está ligado (ADR 0019).

Este ficheiro existe porque **a app já servia inglês e pt-BR a um utilizador
português, e ninguém o sabia**. Com `LANGUAGE_CODE = "pt-pt"`, medido antes de o
catálogo do projecto existir: oito mensagens do DRF saíam em inglês ("Must be a
valid UUID."), seis traziam vocabulário pt-BR ("Use um dos formatos a seguir",
"mídia", "Você"), uma trazia um erro ortográfico do próprio catálogo
("Certifque-se"), e a frase do 429 saía partida ao meio — metade em português,
metade em inglês.

Nada disso aparecia em teste nenhum. A razão é a de sempre nesta casa: **o modo
de falha é silencioso.** Uma mensagem na língua errada não levanta, não falha um
`assert` e não aparece num log; só aparece a quem a lê, e esse não escreve
bilhetes.

## As quatro coisas que isto mede

1. **O `.mo` está compilado e corresponde ao `.po`.** Os `.po` são commitados e
   os `.mo` não (são binários cujo diff ninguém lê), logo o `compilemessages`
   corre no `builder` do Docker e no CI. Um compile esquecido dá uma UI em
   inglês **sem erro nenhum**, e é por isso que o gate é "cada msgid resolve para
   o seu msgstr" e não "o ficheiro existe". Vivido ao escrever esta feature: um
   `.mo` velho deu meia frase certa, que é pior do que a frase errada.
2. **Nenhum marcador pt-BR chega ao utilizador**, por varredura sobre as
   mensagens que esta API consegue emitir. A lista de marcadores é **fechada** e
   o que ela afirma é exactamente isto: estas formas não chegam. Não afirma que
   a frase é de Portugal — gramática não se mede com uma lista de palavras, e as
   duas entradas de concordância do `.po` dizem-no em cada uma.
3. **O mecanismo responde ao `Accept-Language`**, e desde 2026-10-07 com as duas
   línguas a sério: um browser inglês recebe `Content-Language: en` e um
   português (ou brasileiro, de propósito) recebe `pt-pt`. A prova deixou de
   precisar de `override_settings`.

   E **as duas pontas da decisão 9 estão amarradas**: o inglês só pode estar no
   `LANGUAGES` com a lista fechada do `frontend/scripts/check-textos.mjs` vazia.
   O teste lê essa lista e falha nos dois sentidos, porque as duas metades vivem
   em repositórios de linguagens diferentes e essa é a divergência que ninguém
   vê.
4. **O `Vary: Accept-Language` está nas respostas.** Sem ele, uma resposta com
   texto traduzido guardada em cache sai na língua errada ao pedido seguinte. É
   o `LocaleMiddleware` que o põe, e é essa a razão de ele estar no `MIDDLEWARE`
   em vez de um `translation.activate()` numa view.
"""

from __future__ import annotations

import pathlib
import re

from django.conf import settings
from django.test import Client
from django.utils import translation
from rest_framework import exceptions, fields, serializers

#: As formas que não podem chegar a um utilizador português. **Lista fechada**, e
#: o que ela mede são marcadores de vocabulário e não prosa — gramática é regra
#: de revisão, e as entradas de concordância do `.po` dizem-no uma a uma.
#:
#: `Certifque` não é pt-BR: é um erro ortográfico do catálogo `pt_PT` do DRF, e
#: está aqui porque o sítio onde ele se apanha é o mesmo.
MARCADORES_PT_BR = (
    "você",
    "Você",
    "arquivo",
    "registro",
    "deletar",
    "a seguir",
    "planilha",
    "mídia",
    "requisição",
    "essa ação",
    "Certifque",
)

CAMINHO_PO = pathlib.Path(settings.BASE_DIR) / "locale" / "pt_PT" / "LC_MESSAGES" / "django.po"


def _entradas_do_po() -> list[tuple[str, str]]:
    """Os pares `(msgid, msgstr)` do nosso catálogo, lidos do `.po`.

    Um parser de dez linhas e não o `polib`: o que se precisa é dos pares, o
    ficheiro é nosso e tem uma forma só, e uma dependência para isto seria uma
    dependência a mais no `pyproject.toml` por causa de um teste.
    """
    entradas: list[tuple[str, str]] = []
    msgid: str | None = None
    for linha in CAMINHO_PO.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha.startswith("msgid "):
            msgid = linha.removeprefix("msgid ").strip('"')
        elif linha.startswith("msgstr ") and msgid:
            msgstr = linha.removeprefix("msgstr ").strip('"')
            entradas.append((msgid.replace('\\"', '"'), msgstr.replace('\\"', '"')))
            msgid = None
    return entradas


def _mensagens_que_esta_api_emite() -> dict[str, str]:
    """Os msgid que esta API consegue servir, **derivados** e não escritos à mão.

    Percorre os campos que os serializers do `accounts` usam de facto e as
    `APIException` que o DRF levanta nos caminhos desta app. É o método do gate
    de cor: calcular em vez de nomear, para uma mensagem nova entrar na varredura
    sem ninguém a inscrever.

    Os msgid colhem-se **sob `en`** e isso não é detalhe: são objectos lazy, e um
    lazy avalia-se na língua activa — colhidos em português, a chave de procura
    seria a tradução e a varredura não media nada.
    """
    import apps.accounts.serializers as nossos

    classes: set[type] = {fields.Field, serializers.ListSerializer, serializers.Serializer}
    # **Sem `try`/`except`**, e isso é uma afirmação: todos os serializers deste
    # módulo instanciam sem argumentos — medido, zero falham. A primeira versão
    # disto tinha um `except Exception: continue` por precaução, e o `ruff`
    # recusou-o (`S112`), com razão: um `continue` silencioso aqui fazia a
    # varredura encolher sem ninguém saber, que é o modo de falha que este
    # ficheiro inteiro existe para evitar. Se um serializer novo exigir
    # argumentos, isto levanta — e levantar é o comportamento certo.
    for nome in dir(nossos):
        classe = getattr(nossos, nome)
        if isinstance(classe, type) and issubclass(classe, serializers.Serializer):
            classes.update(type(campo) for campo in classe().fields.values())

    with translation.override("en"):
        mensagens: dict[str, str] = {}
        for classe in classes:
            for chave, texto in getattr(classe, "default_error_messages", {}).items():
                mensagens[str(texto)] = f"{classe.__name__}.{chave}"
        for nome in (
            "NotAuthenticated",
            "PermissionDenied",
            "NotFound",
            "MethodNotAllowed",
            "ParseError",
            "UnsupportedMediaType",
            "ValidationError",
            "Throttled",
            "NotAcceptable",
            "APIException",
        ):
            excecao = getattr(exceptions, nome)
            mensagens[str(excecao.default_detail)] = f"{nome}.default_detail"
        # O `Throttled` é a única excepção do DRF com **duas** frases: o
        # `default_detail` e a espera, que ele junta com `ngettext`. Faltavam
        # aqui, e quem o apanhou foi o
        # `test_o_catalogo_nao_tem_entradas_que_ninguem_usa` — as duas entradas
        # do `.po` apareciam órfãs porque este varredor não as conhecia. É o
        # gate de uma direcção a corrigir o varredor da outra, que é o que
        # fechar uma lista nos dois sentidos compra.
        mensagens[str(exceptions.Throttled.extra_detail_singular)] = "Throttled.extra_singular"
        mensagens[str(exceptions.Throttled.extra_detail_plural)] = "Throttled.extra_plural"
    return mensagens


# ---------------------------------------------------------------------------
# 1. O `.mo` está compilado, e corresponde ao `.po`
# ---------------------------------------------------------------------------


def test_o_catalogo_do_projeto_esta_compilado_e_a_valer() -> None:
    """Cada msgid do nosso `.po` resolve para o seu msgstr sob `pt-pt`.

    **É o gate do `compilemessages`**, e falha com a mensagem que diz o que
    fazer. Um msgid que se traduz para si mesmo quer dizer uma de duas coisas, e
    as duas são o mesmo erro: o `.mo` não foi compilado, ou foi compilado antes
    da última alteração ao `.po`.
    """
    entradas = _entradas_do_po()
    assert entradas, f"âncora: o {CAMINHO_PO.name} não tem entradas e o teste não diria nada"

    with translation.override("pt-pt"):
        sem_efeito = [
            msgid for msgid, msgstr in entradas if translation.gettext(msgid) != msgstr
        ]

    assert sem_efeito == [], (
        f"{len(sem_efeito)} entrada(s) do catálogo não estão a valer. O `.mo` não "
        "está compilado ou está desactualizado: corre `uv run manage.py "
        "compilemessages`. Os `.po` são commitados e os `.mo` não — ver o "
        f"cabeçalho do {CAMINHO_PO.name}.\n  " + "\n  ".join(sem_efeito[:5])
    )


def test_o_catalogo_nao_tem_entradas_por_traduzir_nem_fuzzy() -> None:
    """Um `msgstr ""` ou um `#, fuzzy` é uma tradução que não existe.

    O `fuzzy` é o pior dos dois: o `msgfmt` **ignora-o** ao compilar, logo a
    entrada parece estar lá e a mensagem sai em inglês.
    """
    bruto = CAMINHO_PO.read_text(encoding="utf-8")
    assert "#, fuzzy" not in bruto, (
        "entrada `fuzzy` no catálogo: o msgfmt ignora-a ao compilar e a mensagem "
        "sai no msgid (inglês). Revê a tradução e tira a marca."
    )
    vazias = [msgid for msgid, msgstr in _entradas_do_po() if msgstr == ""]
    assert vazias == [], f"entradas sem tradução: {vazias}"


# ---------------------------------------------------------------------------
# 2. Nenhum marcador pt-BR chega ao utilizador
# ---------------------------------------------------------------------------


def test_nenhuma_mensagem_desta_api_sai_com_vocabulario_pt_br() -> None:
    """A varredura, sobre as mensagens que esta API consegue emitir.

    Foi esta varredura que produziu a lista de strings do `.po`: **a lista é
    derivada de uma medição e não adivinhada**, que é o método do gate de cor.
    Enquanto ela existir, uma versão nova do DRF que troque uma frase pt-PT por
    uma pt-BR cai aqui — e um campo novo num serializer entra na varredura sem
    ninguém o inscrever.
    """
    mensagens = _mensagens_que_esta_api_emite()
    assert len(mensagens) > 20, f"âncora: só {len(mensagens)} mensagens, a varredura não varre"

    maus: list[str] = []
    with translation.override("pt-pt"):
        for msgid, origem in sorted(mensagens.items()):
            traduzido = translation.gettext(msgid)
            achados = [m for m in MARCADORES_PT_BR if m in traduzido]
            if achados:
                maus.append(f"{origem}: {achados} em {traduzido!r}")

    assert maus == [], (
        "mensagens com vocabulário pt-BR a chegar ao utilizador. Acrescenta o "
        f"msgid ao {CAMINHO_PO.name} com a tradução pt-PT — o catálogo do "
        "projeto ganha ao do DRF.\n  " + "\n  ".join(maus)
    )


def test_nenhuma_mensagem_desta_api_sai_em_ingles() -> None:
    """A outra metade, e a que a app falhava de forma mais visível.

    Oito mensagens saíam literalmente em inglês — `"Must be a valid UUID."` era
    a resposta a um uuid mal formado, em pt-PT. Um msgid que se traduz para si
    mesmo é uma mensagem sem tradução, e aqui isso é vermelho.

    A excepção são os msgid cuja tradução pt-PT **é** o inglês, que não existem
    nesta lista: nenhuma destas frases é igual nas duas línguas.
    """
    mensagens = _mensagens_que_esta_api_emite()

    em_ingles: list[str] = []
    with translation.override("pt-pt"):
        for msgid, origem in sorted(mensagens.items()):
            if translation.gettext(msgid) == msgid:
                em_ingles.append(f"{origem}: {msgid!r}")

    assert em_ingles == [], (
        "mensagens sem tradução pt-PT, que saem em inglês a quem lê em "
        f"português. Acrescenta-as ao {CAMINHO_PO.name}.\n  " + "\n  ".join(em_ingles)
    )


def _msgids_do_nosso_codigo() -> dict[str, str]:
    """Os `_("...")` que esta app escreve, colhidos do **código fonte**.

    É a direcção que o compilador não cobre e que a varredura do DRF também não:
    uma mensagem nova envolvida em `_()` e esquecida no `.po` sai **em inglês** a
    um utilizador português, sem erro nenhum. É o mesmo modo de falha do `.mo`
    esquecido, por outra porta.

    Lê o texto e não os objectos: um `gettext_lazy` ao nível do módulo já está
    avaliado quando o teste corre, e perseguir os objectos obrigava a enumerar os
    módulos — que é uma lista a manter. O ficheiro é a fonte, e a regex casa a
    forma que este repositório usa (`_(` com um ou mais literais adjacentes).

    **Os comentários são removidos primeiro**, e isso não é zelo: o
    `config/settings/base.py` tem um `_("English")` **dentro de um comentário**, a
    explicar como se liga a segunda língua. Sem esta limpeza, o gate exigia uma
    tradução para uma string que nenhum código emite — e a primeira corrida
    apanhou-a.
    """
    encontrados: dict[str, str] = {}
    for raiz in ("apps", "config"):
        for caminho in sorted(pathlib.Path(settings.BASE_DIR, raiz).rglob("*.py")):
            if "migrations" in caminho.parts:
                continue
            fonte = re.sub(r"^\s*#.*$", "", caminho.read_text(encoding="utf-8"), flags=re.M)
            for bloco in re.finditer(r"\b_\(\s*((?:\s*\"(?:[^\"\\\\]|\\\\.)*\"\s*)+)\)", fonte):
                partes = re.findall(r"\"((?:[^\"\\\\]|\\\\.)*)\"", bloco.group(1))
                encontrados["".join(partes)] = str(caminho.relative_to(settings.BASE_DIR))
    return encontrados


def test_nenhuma_mensagem_nossa_sai_em_ingles() -> None:
    """Cada `_()` do nosso código tem tradução pt-PT, e isso é medido no código.

    Sem este gate, o custo de pôr os msgid em inglês era pago pelo utilizador
    português: uma mensagem nova envolvida em `_()` e esquecida no `.po` sai em
    inglês, e nada no sistema o diz. Com ele, esquecer é vermelho.

    É também o que faz a escolha de msgid em inglês ser simétrica: o inglês sai
    de graça (é o msgid) e o português é **exigido**. No caminho inverso — msgid
    em português — era o inglês que saía em silêncio, e não há gate que o apanhe
    sem uma lista de strings a manter à mão.
    """
    nossos = _msgids_do_nosso_codigo()
    assert len(nossos) >= 15, f"âncora: só {len(nossos)} msgid nossos, a varredura não varre"

    sem_traducao: list[str] = []
    with translation.override("pt-pt"):
        for msgid, origem in sorted(nossos.items()):
            if translation.gettext(msgid) == msgid:
                sem_traducao.append(f"{origem}: {msgid[:60]!r}")

    assert sem_traducao == [], (
        f"{len(sem_traducao)} mensagem(ns) nossa(s) sem tradução pt-PT — saem em "
        f"inglês a quem lê em português. Acrescenta-as ao {CAMINHO_PO.name}.\n  "
        + "\n  ".join(sem_traducao)
    )


def test_o_catalogo_nao_tem_entradas_que_ninguem_usa() -> None:
    """Uma entrada que nenhum código nem o DRF emitem é peso morto.

    A direcção contrária do teste acima, e a razão de ela valer um teste: um
    `.po` cresce por acrescento e ninguém o poda. Uma entrada órfã não quebra
    nada — e é exactamente por isso que fica lá para sempre, a fazer parecer que
    algo está traduzido quando a frase já não existe.

    O que conta como "usada": um msgid do nosso código, ou um msgid que o DRF
    consegue emitir nesta app. As duas fontes são as mesmas que os outros testes
    deste ficheiro usam.
    """
    usadas = set(_msgids_do_nosso_codigo()) | set(_mensagens_que_esta_api_emite())
    orfas = [msgid for msgid, _msgstr in _entradas_do_po() if msgid not in usadas]

    assert orfas == [], (
        "entradas do catálogo que nada emite. Tira-as, ou confirma quem as usa:\n  "
        + "\n  ".join(repr(o) for o in orfas)
    )


# ---------------------------------------------------------------------------
# 3. O mecanismo responde ao `Accept-Language`
# ---------------------------------------------------------------------------


#: A lista fechada do gate de copy do frontend, lida daqui. O caminho é relativo
#: a este ficheiro para o teste correr onde o `pytest` for lançado.
GATE_DE_COPY = pathlib.Path(__file__).resolve().parents[2] / "frontend/scripts/check-textos.mjs"


def _ficheiros_sem_catalogo() -> list[str]:
    """Os ficheiros declarados como **ainda não traduzidos** no gate do frontend.

    Lê o `SEM_CATALOGO` por regex e não por import: é JavaScript, e um `node`
    chamado de dentro de um teste de Python é uma dependência nova na suite para
    ler cinco linhas de uma lista literal.
    """
    fonte = GATE_DE_COPY.read_text(encoding="utf-8")
    bloco = re.search(r"const SEM_CATALOGO = new Set\(\[(.*?)\]\);", fonte, re.DOTALL)
    assert bloco is not None, (
        f"não encontrei o `SEM_CATALOGO` em {GATE_DE_COPY}. Se ele mudou de nome ou de "
        "forma, este teste deixou de medir o que diz medir — arranja-o em vez de o apagar."
    )
    # Sem comentários: a lista vazia tem quatro linhas de prosa lá dentro.
    sem_comentarios = re.sub(r"//.*$", "", bloco.group(1), flags=re.MULTILINE)
    return re.findall(r'"([^"]+)"', sem_comentarios)


def test_o_ingles_so_liga_com_a_lista_vazia() -> None:
    """As duas pontas da decisão 9, amarradas — e falha nos **dois** sentidos.

    A ADR 0019 fez a lista fechada do `check-textos.mjs` o gate de quando o
    inglês liga: "no commit em que a última linha sair". Uma frase numa ADR não
    impede nada, e as duas metades vivem em repositórios de linguagens
    diferentes — é precisamente a forma de divergência que ninguém vê.

    Então o teste lê a lista do frontend e compara-a com o `LANGUAGES` daqui:

    - **inglês servido com a lista cheia** é uma app meio traduzida a dar ao
      leitor inglês uma parede de português onde a tarefa fica difícil;
    - **lista vazia sem inglês servido** é trabalho feito que ninguém recebe, e é
      o estado que passa despercebido por não ter sintoma nenhum.

    Note-se o que isto **não** mede: que a tradução está boa. Mede que as duas
    decisões são a mesma.
    """
    linguas = [codigo for codigo, _ in settings.LANGUAGES]
    por_traduzir = _ficheiros_sem_catalogo()

    assert ("en" in linguas) == (por_traduzir == []), (
        f"as duas pontas da ADR 0019 (decisão 9) divergiram: `LANGUAGES` = {linguas}, "
        f"e o `SEM_CATALOGO` do frontend tem {len(por_traduzir)} ficheiro(s) "
        f"por traduzir ({por_traduzir[:3]}…). Ou a lista esvazia-se, ou o inglês sai "
        "do `LANGUAGES` — a app não serve uma língua em que só metade dos ecrãs está "
        "traduzida."
    )


def test_um_browser_ingles_recebe_ingles() -> None:
    """O outro lado do mesmo: com o inglês ligado, o header escolhe-o de facto.

    O `Content-Language` é a afirmação do servidor sobre a língua em que
    respondeu, e é o que distingue "o inglês está no `LANGUAGES`" de "o inglês
    chega a quem o pede" — duas coisas que um `LocaleMiddleware` mal posto separa
    sem dizer nada.
    """
    resposta = Client().get("/api/v1/auth/sessao", headers={"accept-language": "en-US,en;q=0.9"})

    assert resposta.status_code == 200
    assert resposta.headers.get("Content-Language") == "en"


def test_um_browser_portugues_continua_a_receber_portugues() -> None:
    """E um `pt-BR` também: a ADR 0019 serve-o em pt-PT de propósito."""
    for pedida in ("pt-PT,pt;q=0.9", "pt-BR,pt;q=0.9", "fr-FR,fr;q=0.9"):
        resposta = Client().get("/api/v1/auth/sessao", headers={"accept-language": pedida})

        assert resposta.status_code == 200
        assert resposta.headers.get("Content-Language") == "pt-pt", pedida


def test_o_accept_language_escolhe_a_lingua_da_resposta(transactional_db: None) -> None:
    """A cadeia inteira — middleware, ordem e catálogo — com duas línguas.

    Tinha um `override_settings` a ligar o inglês só aqui, que era a única forma
    de o provar enquanto a app servia uma língua. Desde 2026-10-07 o inglês está
    no `LANGUAGES` e o teste corre contra a configuração a sério, que é o que se
    quer: um `override` prova o mecanismo e não a app.

    O corpo é o **mesmo** nos dois pedidos e a mensagem é do DRF, não nossa: o
    que se afirma é que o `LocaleMiddleware` activou a língua do header antes de
    o serializer construir a frase.
    """
    cliente = Client()
    corpo = {"email": "", "password": ""}

    em_portugues = cliente.post(
        "/api/v1/auth/login",
        data=corpo,
        content_type="application/json",
        headers={"accept-language": "pt-PT"},
    )
    em_ingles = cliente.post(
        "/api/v1/auth/login",
        data=corpo,
        content_type="application/json",
        headers={"accept-language": "en"},
    )

    assert em_portugues.status_code == 400
    assert em_ingles.status_code == 400

    pt = em_portugues.json()["email"][0]
    en = em_ingles.json()["email"][0]

    assert pt != en, (
        "a mesma recusa saiu igual nas duas línguas: o `LocaleMiddleware` não "
        "está no `MIDDLEWARE`, ou está abaixo de quem constrói a resposta."
    )
    assert "branco" in pt, pt
    assert "blank" in en, en


def test_as_respostas_levam_vary_accept_language() -> None:
    """Sem `Vary`, uma cache serve a língua errada ao pedido seguinte.

    É o `LocaleMiddleware` que o põe, e é essa a razão de ele viver no
    `MIDDLEWARE` em vez de um `translation.activate()` numa view — um `activate`
    traduzia a resposta e deixava-a indistinguível de uma noutra língua para
    quem a guarda.
    """
    resposta = Client().get("/api/v1/auth/sessao")

    vary = resposta.headers.get("Vary", "")
    assert "Accept-Language" in vary, f"Vary sem Accept-Language: {vary!r}"


# ---------------------------------------------------------------------------
# 4. A ordem no MIDDLEWARE, afirmada
# ---------------------------------------------------------------------------


def test_o_locale_middleware_esta_acima_do_tenant_middleware() -> None:
    """A língua tem de estar activa quando um service levanta uma recusa.

    As recusas acontecem dentro do âmbito que o `TenantMiddleware` abre, logo a
    língua tem de ser activada antes dele. E depois do `SessionMiddleware`,
    porque o `LocaleMiddleware` olha para a sessão antes do header.

    É uma asserção sobre ordem e não sobre presença porque a presença não basta:
    um `LocaleMiddleware` no fim da lista está instalado e não serve de nada.
    """
    ordem = settings.MIDDLEWARE
    locale = ordem.index("django.middleware.locale.LocaleMiddleware")
    sessao = ordem.index("django.contrib.sessions.middleware.SessionMiddleware")
    tenant = ordem.index("apps.accounts.middleware.TenantMiddleware")

    assert sessao < locale < tenant, (
        "o LocaleMiddleware tem de estar depois do SessionMiddleware e antes do "
        f"TenantMiddleware. Ordem actual: sessão={sessao}, locale={locale}, "
        f"tenant={tenant}."
    )


def test_o_set_language_do_django_nao_esta_encaminhado() -> None:
    """`django.conf.urls.i18n` não entra, e é uma decisão de segurança.

    O `set_language` é um **POST anónimo que escreve um cookie**, que é a família
    de endpoint que o `SECURITY.md` §5 obriga a proteger. E o cookie
    `django_language` **ganha** ao `Accept-Language` no `LocaleMiddleware`: um
    cookie velho passava a mandar no lado da API sem mandar no lado do React, e
    os dois sinais a divergir é exactamente a propriedade que a ADR 0019 compra.
    """
    resposta = Client().post("/i18n/setlang/", data={"language": "en"})

    assert resposta.status_code == 404, (
        "o `/i18n/setlang/` responde: alguém encaminhou o `django.conf.urls.i18n`. "
        "Ver a ADR 0019, decisão 2."
    )
