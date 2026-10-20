"""A extração de um documento, sem modelo nenhum configurado (ADR 0021, fatia 1).

Este ficheiro mede cinco coisas.

**1. Sem modelo configurado, a tentativa é gravada com erro legível e a tarefa não
rebenta.** É o estado de **todo** o projecto hoje: não há cliente de LLM, nem
chave de API, nem rede. O que a fatia 1 entrega é o caminho completo até à
fronteira, e o que esta asserção protege é que a falha fica na base de dados (uma
linha, com `status=erro` e uma frase) e não num log de worker. As recusas de
configuração são três e cada uma tem o seu teste, com o ambiente que a torna
verdadeira: sem modelo, sem chave, e sem preço com um destino que cobra.

Esse ambiente é **fixado** e nunca herdado: a fixture `_extracao_por_configurar`
põe as cinco settings de que a fronteira depende, e a razão está no docstring
dela — uma suite que lê configuração do ambiente afirma coisas diferentes em
máquinas diferentes.

**2. O `payload` guarda-se verbatim e nunca é lido para ramificar.** O que decide
o estado é a **forma** do payload contra o schema, e o conteúdo é escrito como
veio — também quando não valida. Há um teste que o afirma byte a byte, e outro que
percorre o schema e exige que ele **não** tenha campo nenhum que escolha uma
entidade (`product`, `location`, `packaging`): uma string extraída nunca vira uma
chave estrangeira sem uma pessoa a confirmar.

**3. As duas listas fechadas do estado da chamada são iguais.** O `status` do
`agents_extraction` e o `EstadoDaLeitura` do porto do `purchasing` têm os mesmos
quatro valores, em módulos diferentes e por razões diferentes — e é a divergência
entre elas que ninguém veria.

**4. O porto está ligado no arranque.** Sem o `ready()` do `AgentsConfig`, o
`DocumentoOut` servia `extraction: null` para sempre e nenhum teste de documento
falhava. Esta é a asserção que o apanha.

**5. O relógio dos dez minutos.** `a_extrair` enquanto a última tentativa não
acaba e tem menos de dez minutos; `erro` depois. Medido na função pura e através
do HTTP, com o `started_at` recuado.

## Porque é que todos levam `transactional_db`

Além da razão do `tests/test_convites.py` (o `set_config` da RLS), há uma desta
feature: a extração é enfileirada num `transaction.on_commit`, que só corre num
commit a sério. Sem `transactional_db` nenhuma extração aconteceria e este
ficheiro media o vazio.

## E porque é que o `_documento_com_pagina` chama o consumidor da outbox

Porque desde 2026-10-08 o fecho de um documento **publica um evento** em vez de
enfileirar as tarefas (`apps/shared/consumidor.py`), e quem transforma o evento
em trabalho é uma passagem do consumidor — em produção, o `beat`, a cada 5
segundos. O POST deixou de fazer o trabalho: regista-o. O auxiliar faz a
passagem, numa linha, e é a única diferença deste ficheiro em relação à versão
anterior.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts.middleware import SESSION_TENANT_KEY
from apps.accounts.models import Papel, Tenant, User
from apps.accounts.services import BACKEND_DE_SESSAO, conceder_pertenca, criar_tenant
from apps.agents.fronteira import FronteiraLocalDaExtracao
from apps.agents.modelo import (
    DocumentoGrandeDemais,
    ModeloNaoConfigurado,
    RespostaDoModelo,
    ler_documento,
)
from apps.agents.models import EstadoDaExtracao, Extraction
from apps.agents.serializers import LeituraDeFaturaSerializer, LinhaDeFaturaSerializer
from apps.agents.services import chave_de_idempotencia
from apps.agents.tasks import extrair_documento
from apps.purchasing.api import (
    EstadoDaLeitura,
    PaginaDoDocumento,
    fronteira_da_extracao,
)
from apps.purchasing.models import (
    JANELA_DA_EXTRACAO,
    EstadoDoDocumento,
    estado_do_documento,
)
from apps.purchasing.rasterizacao import ImagemNormalizada
from apps.shared.consumidor import ENTREGUE, consumir_outbox
from apps.shared.db import tenant_scope

URL = "/api/v1/documents"

CREDENCIAL_VALIDA = "trigo-fresco-ao-amanhecer-7"

#: Uma credencial de mentira, para os testes cujo facto **não** é a falta de
#: chave. Nenhum deles chega a abrir um socket: a recusa que medem acontece
#: antes da fábrica `cliente()`.
CHAVE_DE_ENSAIO = "sem-valor-nao-e-segredo"

#: Um modelo **com** preço e a tabela que lho dá, fixados juntos: a tabela real
#: vive no `config/settings/base.py` e muda quando o dono muda de fornecedor, e
#: um teste sobre a chave não pode passar a falhar por causa disso.
MODELO_COM_PRECO = "um-modelo-com-preco"
MODELO_SEM_PRECO = "um-modelo-sem-preco"
PRECOS = {MODELO_COM_PRECO: {"input": Decimal("0.23"), "output": Decimal("1.85")}}

PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type /Catalog>>endobj\n"
    b"2 0 obj<</Type /Page>>endobj\n"
    b"%%EOF\n"
)

#: Uma resposta do modelo que **valida**: o cabeçalho de uma fatura simplificada
#: e duas linhas. Os valores vêm do seed das fixtures (a manteiga a 9,40 €), para
#: o que se mede ser uma fatura plausível e não um objecto de teste.
PAYLOAD_VALIDO = {
    "confidence": "0.910",
    "supplier_name": "Frutaria do Mercado",
    "supplier_nif": "212345678",
    "doc_type": "FS",
    "doc_number": "FS 2026/1174",
    "issued_at": "2026-10-06",
    "customer_nif": "",
    "total": "204.40",
    "lines": [
        {
            "position": 2,
            "description": "MANTEIGA C/SAL 250G",
            "quantity": "4.000",
            "unit": "UN",
            "unit_price": "9.4000",
            "vat_rate": "6.000",
            "line_total": "37.60",
            "confidence": "0.880",
        },
        {
            "position": 1,
            "description": "FARINHA T65 25KG",
            "quantity": "2.000",
            "unit": "SC",
            "unit_price": "17.3300",
            "vat_rate": "6.000",
            "line_total": "34.66",
            "confidence": "0.950",
        },
    ],
}


@dataclass(frozen=True, kw_only=True, slots=True)
class Cenario:
    alfa: Tenant
    ana: User


@pytest.fixture(autouse=True)
def _cache_limpa() -> Iterator[None]:
    """O throttle das escritas conta em cache local ao processo — ver o
    `tests/test_documentos.py`."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _rasterizador(monkeypatch: pytest.MonkeyPatch) -> None:
    """A libvips substituída: as páginas ganham imagem sem dependência nativa.

    Autouse porque **toda** a extração passou a precisar de imagem (ADR 0031,
    decisão 1): o modelo é de visão, e sem bytes não há chamada. Sem isto, nesta
    máquina sem libvips, nenhuma página normalizava e a tarefa devolvia
    `paginas_por_normalizar` sem abrir tentativa nenhuma — que é o comportamento
    certo e tornava este ficheiro inteiro uma medição do vazio.
    """
    import apps.purchasing.tasks as tarefas_do_purchasing

    monkeypatch.setattr(
        tarefas_do_purchasing,
        "rasterizar",
        lambda **_: ImagemNormalizada(webp=b"RIFF-encenado", width=1240, height=1754),
    )


@pytest.fixture(autouse=True)
def _extracao_por_configurar() -> Iterator[None]:
    """O estado que este ficheiro mede, fixado em vez de herdado da máquina.

    A premissa do ficheiro é *"não há modelo, não há chave, não há rede"* — e
    até 2026-10-20 ela vinha das omissões do ambiente, o que é o mesmo que dizer
    que vinha do `backend/.env` de quem corre a suite. Dois testes afirmavam
    coisas diferentes em máquinas diferentes por causa disso: o CI (sem `.env`,
    destino OpenAI) via a recusa do **preço**, e a máquina do dono (com
    `AGENTS_CHAT_BASE_URL` para um fornecedor gratuito) via a da **chave**.
    Verde localmente deixava de querer dizer alguma coisa.

    Cinco settings, porque são as cinco de que a fronteira depende: o modelo, as
    duas URL base (a da extração cai na do chat) e as duas chaves. Fixadas aqui
    e não teste a teste porque é o ficheiro inteiro que mede este estado; quem
    mede outro põe o seu `override_settings` por cima, que aninha.
    """
    with override_settings(
        AGENTS_EXTRACTION_MODEL="",
        AGENTS_EXTRACTION_BASE_URL="",
        AGENTS_EXTRACTION_API_KEY="",
        AGENTS_CHAT_BASE_URL="",
        AGENTS_CHAT_API_KEY="",
    ):
        yield


@pytest.fixture
def cenario(transactional_db: None) -> Cenario:
    ana = User.objects.create_user("ana@alfa.pt", CREDENCIAL_VALIDA)
    alfa = criar_tenant(name="Pastelaria Alfa")
    with tenant_scope(alfa.id):
        conceder_pertenca(
            user=ana, tenant_id=alfa.id, role=Papel.OWNER, display_name="Ana Silva"
        )
    return Cenario(alfa=alfa, ana=ana)


def _cliente(cenario: Cenario) -> Client:
    cliente = Client()
    cliente.force_login(cenario.ana, backend=BACKEND_DE_SESSAO)
    sessao = cliente.session
    sessao[SESSION_TENANT_KEY] = str(cenario.alfa.id)
    sessao.save()
    return cliente


def _documento_com_pagina(cliente: Client) -> str:
    """Um documento com um PDF: nasce fechado, e a extração corre na passagem.

    O `consumir_outbox()` é a parte que mudou a 2026-10-08, e é a latência desta
    feature a ser visível num teste: o POST escreve `DocumentoFechado` na outbox e
    mais nada. Em produção é o `beat` que faz esta chamada, a cada 5 segundos;
    aqui é o teste, porque o que ele quer medir é o que acontece **depois** de o
    consumidor passar.

    A fixture `_rasterizador` (autouse) faz a página ganhar imagem na mesma
    passagem, e isso passou a ser **necessário** com a ADR 0031: a extração já
    não abre tentativa nenhuma quando nenhuma página tem imagem, porque sem
    imagem não há nada para mandar a um modelo de visão.
    """
    resposta = cliente.post(
        URL, data={"ficheiro": SimpleUploadedFile("fatura.pdf", PDF, "application/pdf")}
    )
    assert resposta.status_code == 201, resposta.content
    assert consumir_outbox() == {ENTREGUE: 1}
    return resposta.json()["id"]


def _tentativas(tenant_id: UUID, documento_id: str) -> list[Extraction]:
    with tenant_scope(tenant_id):
        return list(
            Extraction.objects.filter(document_id=documento_id).order_by("attempt")
        )


# ---------------------------------------------------------------------------
# 1. Sem modelo configurado
# ---------------------------------------------------------------------------
def test_a_extracao_sem_modelo_grava_a_tentativa_com_erro_legivel(cenario: Cenario) -> None:
    """Uma linha, `status=erro`, uma frase que diz o que falta, e nada rebentou.

    O enfileiramento acontece no `on_commit` do POST, e com
    `CELERY_TASK_ALWAYS_EAGER` a tarefa corre logo — logo o que este teste mede é
    o caminho inteiro do pedido até à linha de extração, sem tocar na tarefa.
    """
    cliente = _cliente(cenario)
    documento_id = _documento_com_pagina(cliente)

    tentativas = _tentativas(cenario.alfa.id, documento_id)

    assert len(tentativas) == 1
    tentativa = tentativas[0]
    assert tentativa.status == EstadoDaExtracao.ERRO
    assert tentativa.attempt == 1
    assert tentativa.started_at is not None
    assert tentativa.finished_at is not None
    assert tentativa.model == ""
    assert tentativa.prompt_version == "1-pt-json"
    assert tentativa.payload == {}
    assert tentativa.cost_eur == Decimal("0")
    assert "AGENTS_EXTRACTION_MODEL" in tentativa.error
    assert "\n  File " not in tentativa.error, "a razão não leva traceback"


def test_o_documento_le_se_em_erro_e_o_painel_traz_a_razao(cenario: Cenario) -> None:
    """O estado derivado chega ao cliente, e a razão com ele.

    É a entrega visível da fatia 1 quando não há modelo: o ecrã não fica à espera
    para sempre, diz `erro` e diz porquê.
    """
    cliente = _cliente(cenario)
    documento_id = _documento_com_pagina(cliente)

    corpo = cliente.get(f"{URL}/{documento_id}").json()

    assert corpo["state"] == EstadoDoDocumento.ERRO
    assert corpo["extraction"]["state"] == EstadoDaLeitura.ERRO
    assert "modelo de extração" in corpo["extraction"]["reason"]
    # Nada de cabeçalho nem de linhas: não houve resposta nenhuma.
    assert corpo["extraction"]["supplier_name"] == ""
    assert corpo["extraction"]["total"] is None
    assert corpo["extraction"]["lines"] == []
    assert corpo["extraction"]["read_at"] is not None


def test_a_tarefa_devolve_erro_e_nao_levanta(cenario: Cenario) -> None:
    """Chamada directamente, a tarefa devolve o estado em vez de propagar.

    Com `CELERY_TASK_EAGER_PROPAGATES` ligado, uma excepção aqui falhava o teste
    — é essa a razão de este teste ser uma chamada directa e não um pedido HTTP.
    """
    cliente = _cliente(cenario)
    documento_id = _documento_com_pagina(cliente)

    resultado = extrair_documento(
        tenant_id=str(cenario.alfa.id), documento_id=documento_id
    )

    assert resultado == "erro"
    # A segunda chamada é a **segunda tentativa**: cada abertura acrescenta uma
    # linha em vez de sobrepor a anterior (ADR 0021, decisão 9).
    tentativas = _tentativas(cenario.alfa.id, documento_id)
    assert [t.attempt for t in tentativas] == [1, 2]
    assert [t.idempotency_key for t in tentativas] == [
        chave_de_idempotencia(documento_id=UUID(documento_id), tentativa=1),
        chave_de_idempotencia(documento_id=UUID(documento_id), tentativa=2),
    ]


def test_um_documento_sem_paginas_nao_gera_tentativa_nenhuma(cenario: Cenario) -> None:
    """Uma linha de extração de um documento sem páginas era um custo a fingir."""
    cliente = _cliente(cenario)
    documento_id = cliente.post(URL, data={}).json()["id"]

    resultado = extrair_documento(
        tenant_id=str(cenario.alfa.id), documento_id=documento_id
    )

    assert resultado == "sem_paginas"
    assert _tentativas(cenario.alfa.id, documento_id) == []


def test_um_documento_de_outro_tenant_nao_e_legivel_pela_tarefa(cenario: Cenario) -> None:
    """A tarefa lê as páginas dentro do âmbito, e um uuid forjado dá zero linhas.

    É o mesmo argumento da ADR 0007 aplicado ao Celery: o `tenant_id` da tarefa
    vem da linha do documento e abre o âmbito; um documento que não lhe pertence
    não é legível, logo não há páginas e não há extração.
    """
    resultado = extrair_documento(
        tenant_id=str(cenario.alfa.id), documento_id=str(uuid4())
    )

    assert resultado == "sem_paginas"


@override_settings(
    AGENTS_EXTRACTION_MODEL=MODELO_COM_PRECO,
    AGENTS_MODEL_PRICES_EUR_PER_MTOKEN=PRECOS,
    AGENTS_EXTRACTION_BASE_URL="",
    AGENTS_CHAT_BASE_URL="",
    AGENTS_EXTRACTION_API_KEY="",
    AGENTS_CHAT_API_KEY="",
)
def test_com_modelo_configurado_e_sem_chave_grava_erro(cenario: Cenario) -> None:
    """Modelo configurado e credencial nenhuma: `erro` com a razão, zero rede.

    Falha **fechada** e numa frase que diz o que configurar. A diferença entre
    "não consegui ler" e "não há chave" é a diferença entre chamar o fornecedor
    e corrigir o deploy.

    O facto medido é **só** a falta de chave, e por isso tudo o que o podia
    tapar está fixado: o modelo tem preço na tabela (que também vai fixada) e as
    URL base estão vazias. Sem isto o teste afirmava coisas diferentes consoante
    o `.env` da máquina — era a recusa do preço que aparecia no CI.
    """
    cliente = _cliente(cenario)
    documento_id = _documento_com_pagina(cliente)

    tentativa = _tentativas(cenario.alfa.id, documento_id)[0]

    assert tentativa.status == EstadoDaExtracao.ERRO
    assert tentativa.model == MODELO_COM_PRECO
    assert "chave de API" in tentativa.error


@override_settings(
    AGENTS_EXTRACTION_MODEL=MODELO_SEM_PRECO,
    AGENTS_MODEL_PRICES_EUR_PER_MTOKEN=PRECOS,
    AGENTS_EXTRACTION_BASE_URL="",
    AGENTS_CHAT_BASE_URL="",
    AGENTS_EXTRACTION_API_KEY=CHAVE_DE_ENSAIO,
)
def test_com_modelo_sem_preco_e_destino_que_cobra_grava_erro(cenario: Cenario) -> None:
    """O outro facto: há chave, mas o destino cobra e o modelo não tem preço.

    Sem preço na tabela o custo gravado é 0 € e o tecto diário em euros nunca
    trava — logo recusa-se, e é a recusa que a revisão de segurança de
    2026-10-15 pediu. Esta é a metade que o ambiente escondia: numa máquina com
    `AGENTS_CHAT_BASE_URL` para um fornecedor gratuito, `_modelo_tem_preco`
    devolve `True` e esta recusa nunca acontecia.

    Com URL base é outro facto (o nível gratuito, que dispensa a tabela) e tem
    teste próprio no `tests/test_extracao_de_faturas.py`.
    """
    cliente = _cliente(cenario)
    documento_id = _documento_com_pagina(cliente)

    tentativa = _tentativas(cenario.alfa.id, documento_id)[0]

    assert tentativa.status == EstadoDaExtracao.ERRO
    assert tentativa.model == MODELO_SEM_PRECO
    assert "AGENTS_MODEL_PRICES_EUR_PER_MTOKEN" in tentativa.error
    assert "chave de API" not in tentativa.error, "a chave está lá: a razão é o preço"


def test_a_fronteira_do_modelo_recusa_sem_modelo_e_acima_do_tecto(
    cenario: Cenario,
) -> None:
    """Duas recusas que acontecem **antes** de qualquer socket. Zero rede.

    A segunda é a da decisão 1 da ADR 0031: acima do tecto de páginas não se
    chama de todo — a alternativa era pagar uma leitura que já se sabe que vai
    ser cortada a meio. Para ela ser *a* recusa que acontece, o que vem antes
    dela na ordem (modelo, chave, preço) tem de estar fixado e satisfeito: era o
    preço que faltava, e no CI era ele que levantava primeiro.
    """
    with pytest.raises(ModeloNaoConfigurado):
        ler_documento(tenant_id=cenario.alfa.id, paginas=())

    paginas = tuple(
        PaginaDoDocumento(
            id=uuid4(),
            position=i,
            file_page_number=i,
            imagem=f"x/{i}.webp",
            qr_payload="",
            normalized=True,
        )
        for i in range(1, 12)
    )
    with override_settings(
        AGENTS_EXTRACTION_MODEL=MODELO_COM_PRECO,
        AGENTS_MODEL_PRICES_EUR_PER_MTOKEN=PRECOS,
        AGENTS_EXTRACTION_API_KEY=CHAVE_DE_ENSAIO,
        AGENTS_EXTRACTION_MAX_PAGES=10,
    ):
        with pytest.raises(DocumentoGrandeDemais):
            ler_documento(tenant_id=cenario.alfa.id, paginas=paginas)


# ---------------------------------------------------------------------------
# 2. O payload: verbatim à escrita, validado à escrita e à leitura
# ---------------------------------------------------------------------------
def test_uma_resposta_valida_da_lido_e_o_painel_completo(
    cenario: Cenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com a fronteira substituída, o documento fica `lido` e o painel enche-se.

    Substitui-se a **fronteira** e não um cliente HTTP: é para isso que ela tem
    nome próprio, e é o que torna este caminho testável sem dependência nenhuma.

    As linhas saem **ordenadas por `position`** mesmo tendo chegado ao contrário
    no payload: a ordem de uma fatura é a do papel e não a da resposta do modelo.
    """
    import apps.agents.tasks as tarefas

    monkeypatch.setattr(
        tarefas,
        "ler_documento",
        lambda **_: RespostaDoModelo(
            payload=PAYLOAD_VALIDO,
            input_tokens=1820,
            output_tokens=310,
            cost_eur=Decimal("0.004231"),
        ),
    )
    cliente = _cliente(cenario)
    documento_id = _documento_com_pagina(cliente)

    tentativa = _tentativas(cenario.alfa.id, documento_id)[0]
    assert tentativa.status == EstadoDaExtracao.LIDO
    assert tentativa.payload == PAYLOAD_VALIDO, "o payload guarda-se verbatim"
    assert tentativa.input_tokens == 1820
    assert tentativa.output_tokens == 310
    assert tentativa.cost_eur == Decimal("0.004231")
    assert tentativa.confidence == Decimal("0.910")

    corpo = cliente.get(f"{URL}/{documento_id}").json()
    assert corpo["state"] == EstadoDoDocumento.LIDO
    extracao = corpo["extraction"]
    assert extracao["state"] == EstadoDaLeitura.LIDO
    assert extracao["supplier_name"] == "Frutaria do Mercado"
    assert extracao["supplier_nif"] == "212345678"
    assert extracao["doc_type"] == "FS"
    assert extracao["issued_at"] == "2026-10-06"
    assert extracao["total"] == "204.40"
    assert [linha["position"] for linha in extracao["lines"]] == [1, 2]
    assert extracao["lines"][0]["description"] == "FARINHA T65 25KG"
    assert extracao["lines"][0]["unit_price"] == "17.3300"
    assert extracao["lines"][0]["quantity"] == "2.000"


def test_uma_resposta_com_a_forma_errada_da_ilegivel_e_guarda_se_igual(
    cenario: Cenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`total` que não é número: `ilegivel`, e o payload fica como veio.

    É a decisão 4 da ADR 0021: o que a validação decide é o **estado**, e o
    conteúdo guarda-se de qualquer maneira — é prova, e uma prova editada não é
    prova.
    """
    import apps.agents.tasks as tarefas

    torto = {"total": "não sei", "lines": [{"position": 1}]}
    monkeypatch.setattr(
        tarefas, "ler_documento", lambda **_: RespostaDoModelo(payload=torto)
    )
    cliente = _cliente(cenario)
    documento_id = _documento_com_pagina(cliente)

    tentativa = _tentativas(cenario.alfa.id, documento_id)[0]
    assert tentativa.status == EstadoDaExtracao.ILEGIVEL
    assert tentativa.payload == torto
    assert tentativa.confidence is None

    corpo = cliente.get(f"{URL}/{documento_id}").json()
    assert corpo["state"] == EstadoDoDocumento.ILEGIVEL
    assert corpo["extraction"]["state"] == EstadoDaLeitura.ILEGIVEL
    assert corpo["extraction"]["lines"] == []


def test_uma_resposta_que_nao_e_um_objecto_da_ilegivel(
    cenario: Cenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uma lista no lugar de um objecto: `ilegivel` e não um `AttributeError`.

    O `data=` de um serializer com um valor que não é um `dict` levanta em vez de
    falhar a validação, e um modelo que devolva uma lista não deve rebentar a
    tarefa. É a razão de existir o `leitura_do_payload`.
    """
    import apps.agents.tasks as tarefas

    monkeypatch.setattr(
        tarefas, "ler_documento", lambda **_: RespostaDoModelo(payload=["a", "b"])
    )
    cliente = _cliente(cenario)
    documento_id = _documento_com_pagina(cliente)

    assert _tentativas(cenario.alfa.id, documento_id)[0].status == (
        EstadoDaExtracao.ILEGIVEL
    )


def test_o_schema_do_payload_nao_tem_campo_que_escolha_uma_entidade() -> None:
    """Nada de extraído escolhe um artigo, uma embalagem ou uma localização.

    A forma de garantir isto não é uma revisão: é o schema **não ter onde o pôr**.
    Este teste percorre os campos dos dois serializers e falha se algum deles
    parecer uma chave estrangeira — que é o diff a travar, porque é o que
    transformaria uma string lida por um modelo numa entrada de stock sem uma
    pessoa pelo meio (CLAUDE.md).
    """
    proibidos = ("product", "packaging", "location", "lot", "_id", "movement")
    campos = [
        *LeituraDeFaturaSerializer().fields,
        *LinhaDeFaturaSerializer().fields,
    ]

    suspeitos = [
        campo for campo in campos if any(marca in campo for marca in proibidos)
    ]

    assert suspeitos == [], (
        f"o schema do payload ganhou campos que escolhem entidades: {suspeitos}. "
        "Uma string extraída nunca vira uma chave estrangeira sem revisão humana "
        "— a revisão é a fatia 2."
    )


# ---------------------------------------------------------------------------
# 3. As duas listas fechadas do estado da chamada
# ---------------------------------------------------------------------------
def test_os_estados_da_extracao_e_da_leitura_sao_a_mesma_lista() -> None:
    """Dois `TextChoices` em dois módulos, com os mesmos quatro valores.

    O do `agents` é o `choices` de uma coluna; o do `purchasing` é o tipo do
    porto. Têm de existir os dois (nenhum módulo decide o vocabulário do outro) e
    têm de ser iguais — e é a divergência entre eles que ninguém veria, porque o
    sintoma seria um `ValueError` no dia em que uma extração tivesse um estado
    novo.
    """
    assert [e.value for e in EstadoDaExtracao] == [e.value for e in EstadoDaLeitura]
    assert [e.value for e in EstadoDaExtracao] == ["pendente", "lido", "ilegivel", "erro"]


# ---------------------------------------------------------------------------
# 4. O porto
# ---------------------------------------------------------------------------
def test_o_porto_da_extracao_esta_ligado_no_arranque() -> None:
    """Sem isto, o `DocumentoOut` servia `extraction: null` para sempre.

    E nenhum teste de documento falhava por causa disso, porque `null` é um valor
    legítimo do contrato. Esta é a asserção que apanha um `ready()` perdido num
    refactor.
    """
    fronteira = fronteira_da_extracao()

    assert isinstance(fronteira, FronteiraLocalDaExtracao)


def test_o_porto_devolve_vazio_para_uma_lista_vazia(cenario: Cenario) -> None:
    """Uma lista de documentos sem nenhum id não faz query nenhuma.

    Parece trivial e não é: é o que impede a listagem de uma página vazia de
    custar uma query ao `agents`.
    """
    assert (
        FronteiraLocalDaExtracao().leituras(tenant_id=cenario.alfa.id, documento_ids=[])
        == {}
    )


# ---------------------------------------------------------------------------
# 5. O relógio dos dez minutos
# ---------------------------------------------------------------------------
def test_o_relogio_da_extracao_passa_de_a_extrair_a_erro() -> None:
    """A função pura, nos dois lados do relógio.

    Sem base de dados e sem HTTP: é uma derivação e testa-se como tal. O que ela
    cobre é a tarefa morta — `finished_at` nulo para sempre —, que sem relógio
    deixava o documento em `a_extrair` até alguém ir à base de dados.
    """
    agora = timezone.now()
    comum = {
        "discarded_at": None,
        "created_at": agora - timedelta(hours=1),
        "page_count": 2,
        "estado_da_leitura": EstadoDaLeitura.PENDENTE,
        "agora": agora,
    }

    assert estado_do_documento(
        leitura_desde=agora - timedelta(minutes=1), **comum
    ) == EstadoDoDocumento.A_EXTRAIR
    assert estado_do_documento(
        leitura_desde=agora - JANELA_DA_EXTRACAO, **comum
    ) == EstadoDoDocumento.ERRO


def test_uma_extracao_presa_le_se_a_extrair_e_depois_erro(cenario: Cenario) -> None:
    """O mesmo, através do HTTP, com a linha da tentativa presa em `pendente`.

    Escreve-se por `update()` e fora de `services.py` de propósito: não há caso de
    uso que prenda uma extração — ela prende-se por um worker morto —, e a
    alternativa era um `freezegun` só para isto.
    """
    cliente = _cliente(cenario)
    documento_id = _documento_com_pagina(cliente)

    with tenant_scope(cenario.alfa.id):
        Extraction.objects.filter(document_id=documento_id).update(
            status=EstadoDaExtracao.PENDENTE,
            finished_at=None,
            started_at=timezone.now() - timedelta(minutes=1),
            updated_at=timezone.now(),
        )
    assert cliente.get(f"{URL}/{documento_id}").json()["state"] == (
        EstadoDoDocumento.A_EXTRAIR
    )

    with tenant_scope(cenario.alfa.id):
        Extraction.objects.filter(document_id=documento_id).update(
            started_at=timezone.now() - JANELA_DA_EXTRACAO - timedelta(seconds=1),
            updated_at=timezone.now(),
        )

    assert cliente.get(f"{URL}/{documento_id}").json()["state"] == EstadoDoDocumento.ERRO


def test_uma_linha_gravada_como_lida_que_ja_nao_valida_serve_se_ilegivel(
    cenario: Cenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A validação **à leitura**, que é a segunda da decisão 4 da ADR 0021.

    Um payload que passou na escrita e já não passa (o schema mudou, ou alguém
    mexeu na linha) não chega ao cliente como se fosse bom. Sem esta segunda
    validação, confiar no `status` gravado era ter validado uma vez só.
    """
    import apps.agents.tasks as tarefas

    monkeypatch.setattr(
        tarefas, "ler_documento", lambda **_: RespostaDoModelo(payload=PAYLOAD_VALIDO)
    )
    cliente = _cliente(cenario)
    documento_id = _documento_com_pagina(cliente)
    assert cliente.get(f"{URL}/{documento_id}").json()["state"] == EstadoDoDocumento.LIDO

    with tenant_scope(cenario.alfa.id):
        Extraction.objects.filter(document_id=documento_id).update(
            payload={"total": "isto não é um número"}, updated_at=timezone.now()
        )

    corpo = cliente.get(f"{URL}/{documento_id}").json()
    assert corpo["state"] == EstadoDoDocumento.ILEGIVEL
    assert corpo["extraction"]["state"] == EstadoDaLeitura.ILEGIVEL
