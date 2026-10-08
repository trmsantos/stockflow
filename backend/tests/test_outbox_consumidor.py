"""O consumidor da outbox e o `beat` (ARCHITECTURE.md §4, passos 9 e 10).

Este ficheiro mede seis coisas, e a primeira é a razão de a feature existir.

**1. Um evento sem handler não desaparece.** É o oposto exacto do que o Celery
fez a 2026-10-08 na máquina do dono: um worker com uma imagem de sete dias
recebeu `purchasing.normalizar_pagina`, respondeu `Received unregistered task …
The message has been ignored and discarded`, e ficou um documento preso em
`a_normalizar` sem rasto nenhum na aplicação. Com a outbox, a linha fica — com
`processed_at` nulo, com a razão em `last_error`, e **visível ao tenant** pela
política. O teste é `test_um_evento_sem_handler_nao_desaparece`.

**2. Os dois âmbitos, na ordem certa.** A tarefa é `tenant_scope_exempt` e
enfileira-se sem `tenant_id`; a linha é lida sob `system_scope()`; e o handler
corre dentro de `tenant_scope(linha.tenant_id)` — medido pelo que ele **vê**: um
handler que leia uma tabela com política vê as linhas do tenant daquela linha e
não as de outro. É a asserção que apanharia um consumidor que esquecesse a
reentrada no âmbito, e que nenhuma revisão apanha, porque o sintoma é zero linhas
sem erro.

**3. Idempotência por `event_id`.** O mesmo evento entregue duas vezes não paga
duas leituras ao modelo. A medida é a contagem de linhas em `agents_extraction`,
que é onde a duplicação custa dinheiro.

**4. Um handler que levanta não perde a linha.** `attempts` sobe, `last_error`
tem a mensagem **e não o traceback**, `processed_at` continua nulo, e a passagem
seguinte volta a tentar — até alguém corrigir o handler, e aí entrega.

**5. O tecto de tentativas.** Ao chegar lá, a linha sai do conjunto de candidatas
e **fica**: nada a marca como processada. Repeti-la é uma decisão humana (pôr o
`attempts` a zero), e o teste faz exactamente esse `UPDATE`.

**6. O caminho completo do `purchasing`.** Um upload publica o evento, o
consumidor dispara os dois handlers, e a rasterização é enfileirada — com o
`services.py` a não ter um único `.delay()`.

## Porque é que quase todos levam `transactional_db`

Duas razões, e as duas são necessárias. O `set_config('app.tenant_id', …, true)`
do `tenant_scope` só reverte no fim da transação de topo, logo com a transação do
pytest-django por fora o âmbito não fechava (é a razão do
`tests/test_convites.py`). E o `transaction.on_commit` dos handlers só corre num
commit a sério: sem isso, nenhuma tarefa era enfileirada e metade deste ficheiro
media o vazio.

## O guarda de âmbito do `conftest.py` está montado aqui, e é meio teste

Nenhum teste deste ficheiro tem a marca `sem_ambito_de_rls`. O guarda lê o
predicado de cada política do catálogo, reconhece o `system_scope()` como âmbito
legítimo **só** para as relações cuja política tem o disjunto `app.scope`, e
levanta em tudo o resto. É ele que transforma "o consumidor reentra no âmbito
antes de tocar em mais nada" numa asserção em vez de uma promessa.
"""

from __future__ import annotations

import ast
import pathlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.accounts.middleware import SESSION_TENANT_KEY
from apps.accounts.models import Papel, Tenant, User
from apps.accounts.services import BACKEND_DE_SESSAO, conceder_pertenca, criar_tenant
from apps.agents.models import Extraction
from apps.purchasing import services as servicos_do_purchasing
from apps.purchasing.events import DocumentoFechado
from apps.purchasing.models import DocumentPage, InvoiceDocument
from apps.purchasing.rasterizacao import ImagemNormalizada
from apps.shared.consumidor import (
    ENTREGUE,
    FALHOU,
    LIMITE_DO_ERRO,
    SEM_HANDLER,
    TETO_DE_TENTATIVAS,
    consumir_outbox,
)
from apps.shared.db import current_tenant, in_system_scope, system_scope, tenant_scope
from apps.shared.events import DomainEvent
from apps.shared.handlers import (
    EventoEntregue,
    Handler,
    handlers_de,
    subscricao,
    tipos_subscritos,
)
from apps.shared.outbox import OutboxEvent, publish
from apps.shared.tasks import consumir_outbox as tarefa_do_consumidor

URL = "/api/v1/documents"

CREDENCIAL_VALIDA = "trigo-fresco-ao-amanhecer-7"

#: Um PDF de uma página, igual ao do `tests/test_documentos.py` e pela mesma
#: razão: o contador de páginas é um varredor de tokens em Python puro, e o que
#: interessa é exactamente o que ele vê.
PDF_DE_UMA_PAGINA = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type /Catalog /Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type /Pages /Kids [3 0 R] /Count 1>>endobj\n"
    b"3 0 obj<</Type /Page /Parent 2 0 R>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


@dataclass(frozen=True, kw_only=True, slots=True)
class _EventoDeEnsaio(DomainEvent):
    """Um evento com handler, encenado por cada teste que precise de um.

    Vive aqui e não em `apps/`: o que se está a medir é o **mecanismo** do
    consumidor, e medi-lo com um evento de domínio real atava o teste às regras
    desse domínio. Os eventos reais têm os seus testes no fim do ficheiro.
    """

    nota: str = ""


@dataclass(frozen=True, kw_only=True, slots=True)
class _EventoSemHandler(DomainEvent):
    """Um evento que **nunca** é subscrito. É o defeito de 2026-10-08 em forma
    de classe: o tipo existe, a linha é escrita, e nada neste processo sabe
    reagir-lhe."""

    nota: str = ""


@dataclass(frozen=True, kw_only=True, slots=True)
class _EventoQueFalha(DomainEvent):
    """Um segundo tipo, para medir que uma linha a falhar não derruba as outras.

    Um tipo e não um segundo handler do mesmo tipo: os handlers de um evento
    correm na mesma transação, logo dois handlers não provavam independência
    nenhuma — provavam o contrário.
    """

    nota: str = ""


@dataclass(kw_only=True, slots=True)
class _Espia:
    """O que um handler encenado viu enquanto corria.

    Mutável de propósito — é um registo de observações, não um DTO. As três
    primeiras respondem à pergunta do âmbito e a última à da idempotência.
    """

    chamadas: int = 0
    tenants: list[UUID | None] = field(default_factory=list)
    em_ambito_de_sistema: list[bool] = field(default_factory=list)
    documentos_vistos: list[set[UUID]] = field(default_factory=list)
    event_ids: list[UUID] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True, slots=True)
class Cenario:
    """Dois estabelecimentos, porque metade deste ficheiro é sobre isolamento."""

    alfa: Tenant
    beta: Tenant
    #: `owner` em Alfa.
    ana: User
    #: Um documento (slot) de cada lado, para um handler ter o que ver.
    documento_de_alfa: UUID
    documento_de_beta: UUID


@pytest.fixture(autouse=True)
def _cache_limpa() -> Iterator[None]:
    """O throttle das escritas conta em cache local ao processo — ver o
    `tests/test_documentos.py`."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def cenario(transactional_db: None) -> Cenario:
    """O cenário, construído **só** por funções de `services.py`."""
    ana = User.objects.create_user("ana@alfa.pt", CREDENCIAL_VALIDA)
    alfa = criar_tenant(name="Pastelaria Alfa")
    beta = criar_tenant(name="Café Beta")

    with tenant_scope(alfa.id):
        conceder_pertenca(
            user=ana, tenant_id=alfa.id, role=Papel.OWNER, display_name="Ana Silva"
        )
        de_alfa = servicos_do_purchasing.criar_documento(
            tenant_id=alfa.id, created_by_id=ana.id, created_by_name="Ana Silva"
        )
    with tenant_scope(beta.id):
        de_beta = servicos_do_purchasing.criar_documento(
            tenant_id=beta.id, created_by_id=None, created_by_name="Dinis Lima"
        )

    return Cenario(
        alfa=alfa,
        beta=beta,
        ana=ana,
        documento_de_alfa=de_alfa.id,
        documento_de_beta=de_beta.id,
    )


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def _publicar(tenant_id: UUID, evento: DomainEvent | None = None) -> OutboxEvent:
    """Escreve um evento na outbox, pelo `publish` e dentro do âmbito."""
    evento = evento or _EventoDeEnsaio(tenant_id=tenant_id, nota="receção")
    with tenant_scope(tenant_id):
        return publish(evento)


def _linha_vista_pelo_tenant(tenant_id: UUID, event_id: UUID) -> OutboxEvent:
    """A linha da outbox, lida **de dentro do âmbito do tenant**.

    Não é um detalhe de conveniência: ler aqui e não sob `system_scope()` é o que
    prova a palavra "visível" de *"a linha fica com `processed_at` nulo e
    visível"*. A política da outbox tem dois disjuntos, e este é o do tenant.
    """
    with tenant_scope(tenant_id):
        return OutboxEvent.objects.get(pk=event_id)


def _repor_tentativas(event_id: UUID, attempts: int = 0) -> None:
    """Põe o `attempts` de uma linha no valor dado, por `update()`.

    Escreve fora de `services.py` de propósito, como o `_recuar_criacao` do
    `tests/test_documentos.py`: **não há caso de uso que repita um evento**. É,
    literalmente, o `UPDATE` em psql que o `apps/shared/consumidor.py` nomeia
    como a decisão humana de voltar a entregar uma linha esgotada — e o teste
    existe para que essa decisão seja uma coisa que funciona e não uma frase num
    docstring.

    Sob `system_scope()` porque é o âmbito de quem administra a outbox, e porque
    é o único que alcança linhas de qualquer tenant.
    """
    with system_scope():
        OutboxEvent.objects.filter(pk=event_id).update(attempts=attempts)


def _desmarcar(event_id: UUID) -> None:
    """Volta a pôr `processed_at` a nulo. Encena a reentrega de um evento.

    O caso real que isto imita: a passagem morreu depois de o handler commitar e
    antes de a mensagem do broker sair, ou duas passagens leram a linha antes de
    a primeira a marcar. Qualquer deles entrega o mesmo evento duas vezes, que é
    a condição que a idempotência existe para tratar.
    """
    with system_scope():
        OutboxEvent.objects.filter(pk=event_id).update(processed_at=None, attempts=0)


def _cliente(user: User, tenant_id: UUID) -> Client:
    cliente = Client()
    cliente.force_login(user, backend=BACKEND_DE_SESSAO)
    sessao = cliente.session
    sessao[SESSION_TENANT_KEY] = str(tenant_id)
    sessao.save()
    return cliente


def _espia_que_le_documentos(espia: _Espia) -> Handler:
    """Um handler que registra o âmbito em que correu e o que viu lá.

    A leitura dos documentos é o coração do teste de âmbito: `InvoiceDocument`
    tem política de RLS **sem** o disjunto `app.scope`, logo esta query devolve
    zero linhas se o consumidor não tiver reentrado em `tenant_scope` — e levanta
    pelo guarda do `conftest.py` se não houver âmbito nenhum.
    """

    def handler(evento: EventoEntregue) -> None:
        espia.chamadas += 1
        espia.tenants.append(current_tenant())
        espia.em_ambito_de_sistema.append(in_system_scope())
        espia.event_ids.append(evento.event_id)
        espia.documentos_vistos.append(
            set(InvoiceDocument.objects.values_list("id", flat=True))
        )

    return handler


# ---------------------------------------------------------------------------
# 1. O defeito de 2026-10-08: um evento sem handler **não desaparece**
# ---------------------------------------------------------------------------
def test_um_evento_sem_handler_nao_desaparece(cenario: Cenario) -> None:
    """A linha fica pendente, com a razão, e visível ao estabelecimento.

    É o contrário do `ignored and discarded` do Celery, e é a razão desta feature
    existir. As três asserções que importam: `processed_at` nulo (ninguém reagiu),
    `last_error` a dizer o que falta (um handler para este tipo), e a linha a ser
    legível **de dentro do âmbito do tenant** — porque um rasto que só o operador
    da base de dados vê não é rasto para quem está a usar o produto.
    """
    linha = _publicar(
        cenario.alfa.id, _EventoSemHandler(tenant_id=cenario.alfa.id, nota="órfã")
    )

    resumo = consumir_outbox()

    assert resumo == {SEM_HANDLER: 1}
    assert handlers_de(_EventoSemHandler.event_type()) == ()
    depois = _linha_vista_pelo_tenant(cenario.alfa.id, linha.id)
    assert depois.processed_at is None, "marcar isto como processado era perdê-lo"
    assert "nenhum handler subscrito" in depois.last_error
    assert _EventoSemHandler.event_type() in depois.last_error


def test_um_evento_sem_handler_esgota_as_tentativas_e_continua_la(
    cenario: Cenario,
) -> None:
    """Sem handler, a linha gasta tentativas e sai do lote — mas não da tabela.

    Gastar tentativas é deliberado e tem uma razão que não é higiene: as
    candidatas saem por `created_at` crescente e em lotes, logo um punhado de
    linhas órfãs **mais antigas** ocupava o lote inteiro em cada passagem e os
    eventos novos nunca eram lidos. Com tecto, uma linha órfã rouba
    `TETO_DE_TENTATIVAS` passagens e sai do caminho — ficando onde se vê.
    """
    linha = _publicar(
        cenario.alfa.id, _EventoSemHandler(tenant_id=cenario.alfa.id, nota="órfã")
    )

    for _ in range(TETO_DE_TENTATIVAS + 3):
        consumir_outbox()

    depois = _linha_vista_pelo_tenant(cenario.alfa.id, linha.id)
    assert depois.attempts == TETO_DE_TENTATIVAS, "o tecto não travou as passagens"
    assert depois.processed_at is None


# ---------------------------------------------------------------------------
# 2. O âmbito: dispensado na tarefa, sistema na leitura, tenant no handler
# ---------------------------------------------------------------------------
def test_a_tarefa_do_consumidor_e_dispensada_do_ambito_do_tenant() -> None:
    """`tenant_scope_exempt` na classe, e enfileirável sem `tenant_id`.

    As duas metades são necessárias: o atributo é o que o `TenantTask.__call__`
    lê para não abrir âmbito, e o `delay()` sem argumentos é o que prova que o
    `apply_async` também o respeita — sem a dispensa, quem enfileira levava um
    `TenantIdRequired` e o `beat` nunca publicava nada.
    """
    assert tarefa_do_consumidor.tenant_scope_exempt is True
    assert tarefa_do_consumidor.name == "shared.consumir_outbox"


@pytest.mark.django_db(transaction=True)
def test_a_tarefa_corre_sem_tenant_e_sem_ambito_nenhum() -> None:
    """Enfileirada sem `tenant_id`, devolve o resumo de uma passagem vazia.

    Com a outbox vazia o resumo é `{}` — e é o que se quer medir aqui: que a
    tarefa **corre**. Sem a dispensa, isto levantava no `delay()`.
    """
    assert tarefa_do_consumidor.delay().get() == {}
    assert current_tenant() is None
    assert in_system_scope() is False


def test_o_handler_corre_no_ambito_do_tenant_da_linha(cenario: Cenario) -> None:
    """A asserção central do passo 9 do `ARCHITECTURE.md`.

    O consumidor lê a linha sob `system_scope()`, **fecha** o bloco, e reentra em
    `tenant_scope(linha.tenant_id)` antes de tocar em mais nada. O que se mede
    não é a chamada: é o que o handler **vê**. O `purchasing_invoicedocument` tem
    política sem o disjunto `app.scope`, logo:

    * se o consumidor não reentrasse no âmbito, esta leitura devolvia zero linhas
      (e o guarda do `conftest.py` levantava, que é a rede por baixo da rede);
    * se reentrasse com o tenant errado, via o documento de Beta.

    Vê o de Alfa e só esse. É também a asserção que prova que o âmbito de sistema
    **não** é um passe geral: dentro dele esta query não veria nada.
    """
    espia = _Espia()
    linha = _publicar(cenario.alfa.id)

    with subscricao(_EventoDeEnsaio, _espia_que_le_documentos(espia)):
        resumo = consumir_outbox()

    assert resumo == {ENTREGUE: 1}
    assert espia.chamadas == 1
    assert espia.tenants == [cenario.alfa.id]
    assert espia.em_ambito_de_sistema == [False], (
        "o handler correu dentro de system_scope(): o bloco tem de fechar antes "
        "de o tenant_scope abrir (ADR 0005)"
    )
    assert espia.documentos_vistos == [{cenario.documento_de_alfa}]
    assert cenario.documento_de_beta not in espia.documentos_vistos[0]
    assert espia.event_ids == [linha.id]
    # E a linha ficou marcada, na mesma transação em que o handler correu.
    assert _linha_vista_pelo_tenant(cenario.alfa.id, linha.id).processed_at is not None


def test_cada_linha_abre_o_ambito_do_seu_tenant(cenario: Cenario) -> None:
    """Duas linhas de dois estabelecimentos, na mesma passagem.

    É o caso que o `system_scope()` existe para servir — o consumidor não tem
    tenant e reclama linhas de todos — e o que ele **não** pode fazer é tratar as
    duas no mesmo âmbito. Cada handler vê o seu documento e nenhum vê o do outro.
    """
    espia = _Espia()
    de_alfa = _publicar(cenario.alfa.id)
    de_beta = _publicar(cenario.beta.id)

    with subscricao(_EventoDeEnsaio, _espia_que_le_documentos(espia)):
        resumo = consumir_outbox()

    assert resumo == {ENTREGUE: 2}
    assert espia.event_ids == [de_alfa.id, de_beta.id], "a ordem é a de created_at"
    assert espia.tenants == [cenario.alfa.id, cenario.beta.id]
    assert espia.documentos_vistos == [
        {cenario.documento_de_alfa},
        {cenario.documento_de_beta},
    ]


# ---------------------------------------------------------------------------
# 3. Idempotência por `event_id`
# ---------------------------------------------------------------------------
def test_o_mesmo_evento_entregue_duas_vezes_chama_o_handler_duas_vezes(
    cenario: Cenario,
) -> None:
    """O consumidor **não** desduplica, e é por isso que os handlers o fazem.

    Esta é a asserção desconfortável, e é a honesta: o mecanismo entrega outra
    vez, com o mesmo `event_id`. A idempotência é do handler e a chave é esse id
    — é o contrato do `ARCHITECTURE.md` §4, e os dois testes seguintes medem-no
    nos handlers reais.
    """
    espia = _Espia()
    linha = _publicar(cenario.alfa.id)

    with subscricao(_EventoDeEnsaio, _espia_que_le_documentos(espia)):
        consumir_outbox()
        _desmarcar(linha.id)
        consumir_outbox()

    assert espia.chamadas == 2
    assert espia.event_ids == [linha.id, linha.id], "é o mesmo evento, duas vezes"


def test_entregar_o_fecho_duas_vezes_nao_paga_duas_leituras(
    cenario: Cenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A idempotência do `agents.handlers.pedir_extracao`, onde ela custa dinheiro.

    `abrir_tentativa` é `max(attempt) + 1` de propósito (ADR 0021, decisão 4):
    cada abertura é uma tentativa nova, não uma sobreposição. Logo uma segunda
    entrega do mesmo evento, sem a verificação do handler, pagava uma segunda
    leitura ao fornecedor do modelo — e a `idempotency_key` única da tabela não o
    impedia, porque a chave da tentativa 2 é diferente da da 1.
    """
    import apps.purchasing.tasks as tarefas_do_purchasing

    monkeypatch.setattr(
        tarefas_do_purchasing,
        "rasterizar",
        lambda **_: ImagemNormalizada(webp=b"RIFF-encenado", width=1240, height=1754),
    )
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = cliente.post(
        URL,
        data={
            "ficheiro": SimpleUploadedFile(
                "fatura.pdf", PDF_DE_UMA_PAGINA, "application/pdf"
            )
        },
    ).json()["id"]
    with tenant_scope(cenario.alfa.id):
        evento_id = OutboxEvent.objects.get(payload__documento_id=documento_id).id

    consumir_outbox()
    _desmarcar(evento_id)
    consumir_outbox()

    with tenant_scope(cenario.alfa.id):
        assert Extraction.objects.filter(document_id=documento_id).count() == 1


def test_entregar_o_fecho_duas_vezes_nao_rasteriza_de_novo_o_que_ja_tem_imagem(
    cenario: Cenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A idempotência do `purchasing.handlers.rasterizar_paginas_pendentes`.

    Não é por marca nenhuma: é o filtro `normalized_at IS NULL`. Depois da
    primeira entrega a página tem imagem, logo a segunda não tem nada para
    enfileirar — e o contador de chamadas ao rasterizador é o que o prova.
    """
    import apps.purchasing.tasks as tarefas_do_purchasing

    chamadas: list[int] = []

    def rasterizador(**_: object) -> ImagemNormalizada:
        chamadas.append(1)
        return ImagemNormalizada(webp=b"RIFF-encenado", width=1240, height=1754)

    monkeypatch.setattr(tarefas_do_purchasing, "rasterizar", rasterizador)
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = cliente.post(
        URL,
        data={
            "ficheiro": SimpleUploadedFile(
                "fatura.pdf", PDF_DE_UMA_PAGINA, "application/pdf"
            )
        },
    ).json()["id"]
    with tenant_scope(cenario.alfa.id):
        evento_id = OutboxEvent.objects.get(payload__documento_id=documento_id).id

    consumir_outbox()
    assert len(chamadas) == 1
    _desmarcar(evento_id)
    consumir_outbox()

    assert len(chamadas) == 1, "a página já tinha imagem e foi rasterizada outra vez"


# ---------------------------------------------------------------------------
# 4. Um handler que levanta
# ---------------------------------------------------------------------------
def _handler_que_levanta(mensagem: str) -> Handler:
    def handler(evento: EventoEntregue) -> None:
        raise RuntimeError(mensagem)

    return handler


def test_um_handler_que_levanta_deixa_a_linha_pendente_com_a_razao(
    cenario: Cenario,
) -> None:
    """`attempts` sobe, `last_error` tem a mensagem, `processed_at` fica nulo.

    E o `last_error` **não** tem traceback: é a regra que o `scan-artefactos.sh`
    e o `agents_extraction.error` já seguem, e a razão é que o `DETAIL` de um
    erro do Postgres leva valores da linha em conflito (SECURITY.md §1). A
    asserção sobre o `File "` é a forma de medir isso sem depender da forma da
    excepção.
    """
    linha = _publicar(cenario.alfa.id)

    with subscricao(_EventoDeEnsaio, _handler_que_levanta("o fornecedor não respondeu")):
        resumo = consumir_outbox()

    assert resumo == {FALHOU: 1}
    depois = _linha_vista_pelo_tenant(cenario.alfa.id, linha.id)
    assert depois.attempts == 1
    assert depois.processed_at is None
    assert depois.last_error == "RuntimeError: o fornecedor não respondeu"
    assert "File " not in depois.last_error, "a razão não leva traceback"
    assert "Traceback" not in depois.last_error


def test_a_passagem_seguinte_volta_a_tentar_e_entrega_quando_o_handler_sara(
    cenario: Cenario,
) -> None:
    """Duas falhas, depois uma entrega. É o ponto inteiro de não perder a linha.

    A terceira passagem corre com um handler que funciona — que é o que acontece
    na vida real depois de um deploy — e a linha fecha: `processed_at` escrito e
    `last_error` limpo, porque uma razão de erro ao lado de um `processed_at`
    preenchido mandava alguém investigar um problema resolvido.
    """
    espia = _Espia()
    linha = _publicar(cenario.alfa.id)

    with subscricao(_EventoDeEnsaio, _handler_que_levanta("a base de dados caiu")):
        consumir_outbox()
        consumir_outbox()
    intermedia = _linha_vista_pelo_tenant(cenario.alfa.id, linha.id)

    with subscricao(_EventoDeEnsaio, _espia_que_le_documentos(espia)):
        resumo = consumir_outbox()

    assert intermedia.attempts == 2
    assert intermedia.processed_at is None
    assert resumo == {ENTREGUE: 1}
    assert espia.chamadas == 1
    depois = _linha_vista_pelo_tenant(cenario.alfa.id, linha.id)
    assert depois.processed_at is not None
    assert depois.last_error == ""
    assert depois.attempts == 3, "as tentativas falhadas contam-se, e ficam escritas"


def test_um_handler_que_levanta_desfaz_o_que_escreveu(cenario: Cenario) -> None:
    """O `processed_at` commita **com** os handlers, logo um erro desfaz tudo.

    O handler descarta um documento — uma escrita a sério, pelo `services.py` — e
    depois levanta. Nada fica: nem o `discarded_at`, nem a marca na outbox. É a
    propriedade que torna a reentrega segura, e é a razão de a marca não ser
    escrita numa transação à parte: com duas transações haveria uma janela em que
    o efeito está feito e a marca não, e aí a correcção passava a depender
    inteiramente da idempotência do handler.
    """
    linha = _publicar(cenario.alfa.id)

    def handler(evento: EventoEntregue) -> None:
        documento = InvoiceDocument.objects.get(pk=cenario.documento_de_alfa)
        servicos_do_purchasing.descartar_documento(
            tenant_id=evento.tenant_id, documento=documento
        )
        raise RuntimeError("a meio")

    with subscricao(_EventoDeEnsaio, handler):
        assert consumir_outbox() == {FALHOU: 1}

    with tenant_scope(cenario.alfa.id):
        documento = InvoiceDocument.objects.get(pk=cenario.documento_de_alfa)
        assert documento.discarded_at is None
    assert _linha_vista_pelo_tenant(cenario.alfa.id, linha.id).processed_at is None


def test_um_handler_que_levanta_nao_rouba_a_vez_aos_outros(cenario: Cenario) -> None:
    """Uma linha a falhar não derruba a passagem: as outras são tratadas.

    É a razão de o `except` ser por linha e largo. Sem ele, a primeira excepção
    acabava a passagem e as linhas seguintes esperavam cinco segundos por cada
    retentativa da primeira.
    """
    espia = _Espia()
    primeira = _publicar(cenario.alfa.id, _EventoQueFalha(tenant_id=cenario.alfa.id))
    segunda = _publicar(cenario.beta.id)

    with (
        subscricao(_EventoQueFalha, _handler_que_levanta("sempre")),
        subscricao(_EventoDeEnsaio, _espia_que_le_documentos(espia)),
    ):
        resumo = consumir_outbox()

    assert resumo == {FALHOU: 1, ENTREGUE: 1}
    assert _linha_vista_pelo_tenant(cenario.alfa.id, primeira.id).processed_at is None
    assert _linha_vista_pelo_tenant(cenario.beta.id, segunda.id).processed_at is not None


def test_a_razao_e_cortada_na_primeira_linha_e_no_limite(cenario: Cenario) -> None:
    """O corte é estrutural: a primeira linha da mensagem, com um tecto.

    A primeira linha é onde o psycopg põe a fronteira entre o que aconteceu e os
    valores da linha em conflito (`DETAIL: Key (…)=(…)`), e esta coluna é lida no
    admin. Não é um scrubber de padrões — o `config/log.py` argumenta por extenso
    contra esses —, é o sítio onde a mensagem deixa de descrever o erro e passa a
    citar dados.
    """
    linha = _publicar(cenario.alfa.id)
    mensagem = "falhou a escrever\nDETAIL: Key (nif)=(212345678) already exists."

    with subscricao(_EventoDeEnsaio, _handler_que_levanta(mensagem)):
        consumir_outbox()

    razao = _linha_vista_pelo_tenant(cenario.alfa.id, linha.id).last_error
    assert razao == "RuntimeError: falhou a escrever"
    assert "212345678" not in razao

    _desmarcar(linha.id)
    with subscricao(_EventoDeEnsaio, _handler_que_levanta("x" * (LIMITE_DO_ERRO * 2))):
        consumir_outbox()

    assert (
        len(_linha_vista_pelo_tenant(cenario.alfa.id, linha.id).last_error)
        == LIMITE_DO_ERRO
    )


# ---------------------------------------------------------------------------
# 5. O tecto de tentativas
# ---------------------------------------------------------------------------
def test_ao_chegar_ao_tecto_a_linha_sai_do_lote_e_nao_e_marcada(
    cenario: Cenario,
) -> None:
    """Esgotada é esgotada: o handler deixa de ser chamado e a linha **fica**.

    O que **não** acontece é o que interessa: ninguém lhe escreve o
    `processed_at`. Marcar uma linha que nunca foi entregue era perder o evento
    com um nome bonito — e é exactamente o `ignored and discarded` do Celery,
    numa tabela.

    Quem a vigia é a métrica do `ARCHITECTURE.md` §8 (*"outbox com itens > 10
    min"*): a linha continua a contar como pendente, para sempre, até alguém
    decidir o que fazer com ela.
    """
    espia = _Espia()
    linha = _publicar(cenario.alfa.id)

    def handler(evento: EventoEntregue) -> None:
        espia.chamadas += 1
        raise RuntimeError("sempre a mesma coisa")

    with subscricao(_EventoDeEnsaio, handler):
        for _ in range(TETO_DE_TENTATIVAS + 4):
            consumir_outbox()

    assert espia.chamadas == TETO_DE_TENTATIVAS, (
        "sem tecto, uma linha envenenada é tentada para sempre e ocupa o lote"
    )
    depois = _linha_vista_pelo_tenant(cenario.alfa.id, linha.id)
    assert depois.attempts == TETO_DE_TENTATIVAS
    assert depois.processed_at is None
    assert depois.last_error == "RuntimeError: sempre a mesma coisa"


def test_por_o_attempts_a_zero_volta_a_entregar_a_linha(cenario: Cenario) -> None:
    """A decisão humana de repetir uma linha esgotada, exercitada.

    É o `UPDATE` que o `apps/shared/consumidor.py` nomeia — hoje em psql, porque
    a outbox não está no admin (ADR 0007: só lá entram modelos sem política) e não
    há comando de gestão. O teste existe para que o caminho de recuperação seja
    uma coisa que funciona, e não uma frase.
    """
    espia = _Espia()
    linha = _publicar(cenario.alfa.id)

    with subscricao(_EventoDeEnsaio, _handler_que_levanta("enquanto durar")):
        for _ in range(TETO_DE_TENTATIVAS):
            consumir_outbox()

    _repor_tentativas(linha.id)
    with subscricao(_EventoDeEnsaio, _espia_que_le_documentos(espia)):
        resumo = consumir_outbox()

    assert resumo == {ENTREGUE: 1}
    assert espia.chamadas == 1
    assert _linha_vista_pelo_tenant(cenario.alfa.id, linha.id).processed_at is not None


def test_uma_linha_ja_processada_nao_e_tratada_outra_vez(cenario: Cenario) -> None:
    """O `processed_at` é o que tira a linha do caminho, e tira-o de vez."""
    espia = _Espia()
    _publicar(cenario.alfa.id)

    with subscricao(_EventoDeEnsaio, _espia_que_le_documentos(espia)):
        consumir_outbox()
        consumir_outbox()
        consumir_outbox()

    assert espia.chamadas == 1


def test_o_lote_limita_quantas_linhas_uma_passagem_trata(cenario: Cenario) -> None:
    """Uma passagem trata `lote` linhas e deixa as outras para a seguinte.

    O tecto existe pelo lado do tempo: uma passagem que tratasse a outbox inteira
    depois de uma paragem longa passava o `task_soft_time_limit` e era morta a
    meio, com o `beat` a empilhar passagens novas entretanto.
    """
    espia = _Espia()
    for _ in range(3):
        _publicar(cenario.alfa.id)

    with subscricao(_EventoDeEnsaio, _espia_que_le_documentos(espia)):
        primeira = consumir_outbox(lote=2)
        segunda = consumir_outbox(lote=2)

    assert primeira == {ENTREGUE: 2}
    assert segunda == {ENTREGUE: 1}
    assert espia.chamadas == 3


# ---------------------------------------------------------------------------
# 6. O caminho completo do `purchasing`
# ---------------------------------------------------------------------------
def test_os_dois_handlers_do_documento_estao_subscritos_no_arranque() -> None:
    """Sem isto, um upload escrevia na outbox e nada reagia — em silêncio.

    É o gémeo do `test_o_porto_da_extracao_esta_ligado_no_arranque`: um `ready()`
    perdido num refactor não falha teste nenhum, porque uma linha pendente é um
    estado legítimo. Esta é a asserção que o apanha, e exige **dois** handlers de
    **dois** módulos, que é a forma de a inversão de dependência ser verificável.
    """
    from apps.agents.handlers import pedir_extracao
    from apps.purchasing.handlers import rasterizar_paginas_pendentes

    assert DocumentoFechado.event_type() in tipos_subscritos()
    # Conjunto e não tuplo: a ordem é a do `INSTALLED_APPS` (os `ready()` correm
    # por essa ordem) e não é contrato — os dois handlers correm na mesma
    # transação e nenhum depende do outro. O que é contrato é que são **dois**, e
    # de dois módulos: é isso que torna a inversão de dependência verificável.
    assert set(handlers_de(DocumentoFechado.event_type())) == {
        rasterizar_paginas_pendentes,
        pedir_extracao,
    }


def test_um_upload_publica_o_evento_e_o_consumidor_enfileira_a_rasterizacao(
    cenario: Cenario, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O caminho inteiro, do POST à imagem, com a outbox no meio.

    Três momentos, e é a ordem deles que é a entrega desta feature:

    1. depois do POST há **uma linha na outbox** e a página **não** tem imagem.
       É a latência de 0–5 s a ser visível num teste: o pedido não faz o
       trabalho, só o regista;
    2. a passagem do consumidor dispara os dois handlers;
    3. a página fica normalizada e a extração tem uma tentativa.

    O rasterizador é substituído na **fronteira** (`tarefas.rasterizar`) e não um
    decoder: é para isso que ela tem nome próprio, e é o que torna este caminho
    medível numa máquina sem a libvips.
    """
    import apps.purchasing.tasks as tarefas_do_purchasing

    monkeypatch.setattr(
        tarefas_do_purchasing,
        "rasterizar",
        lambda **_: ImagemNormalizada(webp=b"RIFF-encenado", width=1240, height=1754),
    )
    cliente = _cliente(cenario.ana, cenario.alfa.id)

    resposta = cliente.post(
        URL,
        data={
            "ficheiro": SimpleUploadedFile(
                "fatura.pdf", PDF_DE_UMA_PAGINA, "application/pdf"
            )
        },
    )

    assert resposta.status_code == 201, resposta.content
    documento_id = resposta.json()["id"]
    with tenant_scope(cenario.alfa.id):
        pendentes = list(
            OutboxEvent.objects.filter(
                event_type=DocumentoFechado.event_type(), processed_at__isnull=True
            )
        )
        assert len(pendentes) == 1
        assert pendentes[0].payload["documento_id"] == documento_id
        assert DocumentPage.objects.get(document_id=documento_id).normalized_at is None
        assert not Extraction.objects.filter(document_id=documento_id).exists()

    assert consumir_outbox() == {ENTREGUE: 1}

    with tenant_scope(cenario.alfa.id):
        pagina = DocumentPage.objects.get(document_id=documento_id)
        assert pagina.normalized_at is not None
        assert pagina.width == 1240
        assert Extraction.objects.filter(document_id=documento_id).count() == 1
        assert OutboxEvent.objects.get(pk=pendentes[0].id).processed_at is not None


def test_fechar_uma_captura_publica_um_evento_e_so_um(cenario: Cenario) -> None:
    """Dois toques no botão de fechar dão uma linha na outbox, não duas.

    A repetibilidade do fecho (ADR 0020, decisão 1g) é garantida pelo lock do
    serviço, e o que ela protege agora é a outbox: duas linhas eram duas
    extrações, que é dinheiro a dobrar pelo mesmo documento. A asserção mudou de
    sítio — era sobre `Extraction` — porque a causa mudou de sítio.
    """
    cliente = _cliente(cenario.ana, cenario.alfa.id)
    documento_id = cliente.post(URL, data={}).json()["id"]
    cliente.post(
        f"{URL}/{documento_id}/files",
        data={
            "ficheiro": SimpleUploadedFile(
                "pagina.pdf", PDF_DE_UMA_PAGINA, "application/pdf"
            )
        },
    )

    primeiro = cliente.post(f"{URL}/{documento_id}/closing", data={})
    segundo = cliente.post(f"{URL}/{documento_id}/closing", data={})

    assert primeiro.status_code == 200
    assert segundo.status_code == 200
    with tenant_scope(cenario.alfa.id):
        assert (
            OutboxEvent.objects.filter(
                event_type=DocumentoFechado.event_type()
            ).count()
            == 1
        )


def _chamadas_no_ficheiro(modulo: Any) -> set[str]:
    """Os nomes de todas as chamadas por atributo de um módulo, lidos do código.

    Por AST e não por `in` no texto. A primeira versão deste teste procurava a
    string `".delay("` no ficheiro e **falhou** — apanhou o próprio docstring do
    `enfileirar_trabalho_do_documento`, que explica por extenso o mecanismo que
    deixou de usar. Uma prosa que cita o que proíbe é exactamente o que uma
    árvore de sintaxe distingue de uma chamada e um `in` não.
    """
    arvore = ast.parse(
        pathlib.Path(modulo.__file__).read_text(encoding="utf-8"), type_comments=False
    )
    return {
        no.func.attr
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
    }


def test_o_services_do_purchasing_nao_enfileira_nada_directamente() -> None:
    """Nenhum `.delay()` nem `apply_async` no `services.py`. **Medido no código.**

    É a regra do `CLAUDE.md` (*"efeitos secundários em Celery via outbox"*) na
    única forma em que ela é verificável sem um worker: o ficheiro que contém os
    casos de uso não conhece o broker. Quem enfileira são os `handlers.py`, a
    reagir a uma linha que já commitou.

    Estático e não por execução, porque o que se quer proibir é a **escrita** da
    chamada e não a sua passagem por um teste: um `.delay()` num ramo que nenhum
    teste percorre é precisamente o que escaparia a tudo o resto.
    """
    chamadas = _chamadas_no_ficheiro(servicos_do_purchasing)

    assert "delay" not in chamadas
    assert "apply_async" not in chamadas
    assert "on_commit" not in chamadas, (
        "um efeito agendado num on_commit do serviço é o mecanismo que a outbox "
        "substituiu: o que não commitar com a transação não existe"
    )


# ---------------------------------------------------------------------------
# O registo de handlers, em si
# ---------------------------------------------------------------------------
def test_subscrever_o_mesmo_handler_duas_vezes_nao_o_duplica() -> None:
    """Um `ready()` corre mais de uma vez em caminhos de teste do Django.

    Sem idempotência no registo, o handler da rasterização ficava subscrito duas
    vezes e cada documento pagava duas extrações.
    """
    from apps.purchasing.handlers import registar_handlers

    antes = handlers_de(DocumentoFechado.event_type())
    registar_handlers()
    registar_handlers()

    assert handlers_de(DocumentoFechado.event_type()) == antes


def test_o_registo_aceita_o_nome_do_tipo_para_uma_classe_renomeada() -> None:
    """A transição que o `apps/shared/events.py` descreve, exercitada.

    Renomear uma classe de evento muda o `event_type()` e deixa linhas na outbox
    com o nome antigo. Subscrever por string é como o mesmo handler trata os dois
    durante a transição — e sem isso aquelas linhas ficavam pendentes para sempre.
    """
    nome_antigo = "apps.purchasing.events.DocumentoPronto"
    espia = _Espia()

    with subscricao(nome_antigo, _espia_que_le_documentos(espia)):
        assert handlers_de(nome_antigo) != ()

    assert handlers_de(nome_antigo) == ()


def test_a_subscricao_de_um_bloco_restaura_o_que_estava_la(cenario: Cenario) -> None:
    """O gestor de contexto não leva consigo os handlers de produção."""
    antes = handlers_de(DocumentoFechado.event_type())

    with subscricao(DocumentoFechado, _handler_que_levanta("encenado")):
        assert len(handlers_de(DocumentoFechado.event_type())) == len(antes) + 1

    assert handlers_de(DocumentoFechado.event_type()) == antes


def test_publicar_o_mesmo_evento_duas_vezes_e_violacao_de_unicidade(
    cenario: Cenario,
) -> None:
    """A outra metade da idempotência: a chave primária **é** o `event_id`.

    Dois `publish()` do mesmo evento não dão duas linhas — dão um erro. É a
    propriedade que o `apps/shared/outbox.py` declara e a razão de a entrega
    dupla só poder vir do consumidor, nunca de quem publica.
    """
    from django.db import IntegrityError

    evento = _EventoDeEnsaio(tenant_id=cenario.alfa.id, nota="uma vez")
    _publicar(cenario.alfa.id, evento)

    with pytest.raises(IntegrityError), tenant_scope(cenario.alfa.id):
        publish(evento)


def test_um_evento_de_um_tenant_que_ja_nao_existe_nao_derruba_a_passagem(
    cenario: Cenario,
) -> None:
    """O preço nomeado no `apps/shared/outbox.py`: `tenant_id` não é ForeignKey.

    *"Nada impede uma linha com um `tenant_id` que já não existe."* O consumidor
    abre o âmbito desse tenant de qualquer forma — o `set_config` não consulta a
    tabela de tenants — e o handler vê zero linhas de tudo. O que **não** pode
    acontecer é a passagem inteira morrer por causa dela.
    """
    espia = _Espia()
    fantasma = uuid4()
    with system_scope():
        OutboxEvent.objects.create(
            id=uuid4(),
            tenant_id=fantasma,
            event_type=_EventoDeEnsaio.event_type(),
            payload={"tenant_id": str(fantasma)},
        )
    _publicar(cenario.alfa.id)

    with subscricao(_EventoDeEnsaio, _espia_que_le_documentos(espia)):
        resumo = consumir_outbox()

    assert resumo == {ENTREGUE: 2}
    assert espia.documentos_vistos[0] == set(), "um tenant que não existe não tem nada"
    assert espia.documentos_vistos[1] == {cenario.documento_de_alfa}
