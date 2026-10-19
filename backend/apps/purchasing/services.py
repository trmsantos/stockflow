"""Os casos de uso do documento de fornecedor. **Única forma de escrever.**

Uma função por caso de uso, cada uma `@transaction.atomic` (um savepoint dentro
da transação do pedido — ARCHITECTURE.md §4.6), e nenhuma delas sabe o que é um
status HTTP: as recusas são `RecusaDeDocumento` com um `code` estável, e quem o
traduz em status é o `views.py`.

Os seis casos de uso, que são exactamente os sete endpoints da decisão 9 da ADR
0021 menos os três que só leem:

| Função | Quem a chama |
|---|---|
| `criar_documento` | `POST /documents` — o slot do QR, ou o upload de um só gesto |
| `anexar_ficheiro` | `POST /documents/<id>/files` |
| `fechar_documento` | `POST /documents/<id>/closing` |
| `descartar_documento` | `DELETE /documents/<id>` |
| `registar_normalizacao` | a tarefa `normalizar_pagina` |
| `limpar_slots_expirados` | a tarefa com o mesmo nome |

## Os bytes e a transação

O ficheiro é escrito no `MEDIA_ROOT` **dentro** da transação, depois de a linha
existir. Fica nomeado o que isso custa: se a transação reverter, os bytes ficam
no disco sem linha que lhes aponte. A escolha é deliberada — a alternativa
(`transaction.on_commit`) perde os bytes se o processo morrer entre o commit e a
escrita, e perder a fotografia de uma fatura é pior do que deixar um ficheiro
órfão. A purga dos órfãos é a mesma tarefa que a segunda pergunta do dono vai
decidir (quanto tempo se guarda o original), e **não existe hoje**.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.catalog import api as catalog_api
from apps.inventory import api as inventory_api
from apps.purchasing.events import DocumentoFechado, StockReceived
from apps.purchasing.ficheiros import (
    caminho_da_imagem,
    caminho_dentro_do_media,
    caminho_do_ficheiro,
)
from apps.purchasing.models import (
    JANELA_DO_SLOT,
    PAGINAS_POR_DOCUMENTO,
    DocumentFile,
    DocumentPage,
    InvoiceDocument,
    OrigemDoDocumento,
    Receipt,
    ReceiptLine,
)
from apps.purchasing.rasterizacao import ImagemNormalizada
from apps.purchasing.selectors import DOC_TIPO_QUE_SUBTRAI, slots_expirados
from apps.shared.outbox import OutboxEvent, publish

__all__ = [
    "CODIGOS_DE_RECUSA_DE_DOCUMENTO",
    "CODIGO_DOCUMENTO_DESCARTADO",
    "CODIGO_DOCUMENTO_FECHADO",
    "CODIGO_DOCUMENTO_SEM_PAGINAS",
    "CODIGO_PAGINAS_EXCEDIDAS",
    "FicheiroRecebido",
    "RecusaDeDocumento",
    "anexar_ficheiro",
    "criar_documento",
    "descartar_documento",
    "enfileirar_trabalho_do_documento",
    "fechar_documento",
    "limpar_slots_expirados",
    "registar_normalizacao",
]

logger = logging.getLogger(__name__)

#: Anexar a um documento que já foi fechado (409). Um ficheiro fecha-se a si
#: mesmo (ADR 0021, decisão 9), logo este é também o que recusa um segundo
#: ficheiro num documento criado com ficheiro.
CODIGO_DOCUMENTO_FECHADO = "documento_fechado"

#: Escrever num documento descartado (409). Descartar é dizer "isto não
#: interessa"; voltar a escrever-lhe é um engano de cliente, não um caso de uso.
CODIGO_DOCUMENTO_DESCARTADO = "documento_descartado"

#: Fechar um documento sem página nenhuma (409). Fechar é dizer "não vêm mais
#: páginas", e dizê-lo de um documento vazio pedia uma extração de nada. O slot
#: vazio morre pelo relógio e não por uma pessoa (ADR 0020, decisão 2).
CODIGO_DOCUMENTO_SEM_PAGINAS = "documento_sem_paginas"

#: Mais páginas do que o teto do módulo (400).
CODIGO_PAGINAS_EXCEDIDAS = "paginas_excedidas"

#: A lista fechada, contra a qual o mapa de status do `views.py` é afirmado por
#: um teste: um código sem entrada no mapa apareceria como 500.
CODIGOS_DE_RECUSA_DE_DOCUMENTO: frozenset[str] = frozenset(
    {
        CODIGO_DOCUMENTO_FECHADO,
        CODIGO_DOCUMENTO_DESCARTADO,
        CODIGO_DOCUMENTO_SEM_PAGINAS,
        CODIGO_PAGINAS_EXCEDIDAS,
    }
)

DETALHE_DOCUMENTO_FECHADO = _(
    "This document is closed and does not take more pages. Open a new one."
)
DETALHE_DOCUMENTO_DESCARTADO = _("This document was discarded.")
DETALHE_DOCUMENTO_SEM_PAGINAS = _(
    "This document has no pages yet, so there is nothing to close."
)
DETALHE_PAGINAS_EXCEDIDAS = _("A document takes at most {limite} pages.")

#: Quantos bytes de cada vez ao ler o ficheiro para o disco e para o digest. 64
#: KiB é o compromisso habitual: grande o suficiente para o syscall não dominar,
#: pequeno o suficiente para um ficheiro de 12 MiB não viver em memória.
BLOCO = 64 * 1024


class RecusaDeDocumento(Exception):
    """Recusa com um `code` estável no corpo, que é o que o cliente ramifica.

    A mesma forma da `Recusa` do `accounts` e pela mesma razão: o status HTTP não
    basta para ramificar, e um service que soubesse status HTTP era um service a
    saber HTTP. O mapa de códigos para status vive no `views.py`.
    """

    def __init__(self, codigo: str, detalhe: object) -> None:
        super().__init__(detalhe)
        self.codigo = codigo
        self.detalhe = detalhe


class FicheiroRecebido:
    """O que o serializer entrega ao serviço: bytes validados e o tipo real.

    Não é um `dataclass` de propósito — leva um ficheiro aberto, que não é
    serializável nem congelável. O que esta classe compra é a **garantia de
    ordem**: um `UploadedFile` cru não diz se alguém já olhou para os seus bytes,
    e esta só existe depois de o serializer ter decidido o tipo real, o tamanho e
    o número de páginas. O serviço não revalida nada, e não precisa.
    """

    def __init__(
        self,
        *,
        ficheiro,
        tipo: str,
        original_filename: str,
        byte_size: int,
        paginas: int,
    ) -> None:
        self.ficheiro = ficheiro
        self.tipo = tipo
        self.original_filename = original_filename
        self.byte_size = byte_size
        self.paginas = paginas


def enfileirar_trabalho_do_documento(
    *, tenant_id: UUID, documento_id: UUID
) -> OutboxEvent:
    """O **único** ponto onde o trabalho de um documento é agendado.

    Uma escrita: a linha do `DocumentoFechado` na outbox, na mesma transação que
    fechou o documento. O que fazer com ele é de quem o subscreve — hoje o
    `handlers.py` do `purchasing` (rasterizar as páginas sem imagem) e o do
    `agents` (pedir a leitura ao modelo), e esta função não conhece nenhum dos
    dois.

    ## O que aqui estava escrito, e porque é que deixou de ser verdade

    Até 2026-10-08 esta função usava `transaction.on_commit` + `.delay()` e tinha
    neste sítio uma divergência deliberada ao `CLAUDE.md` (*"efeitos secundários
    em Celery via outbox"*), com uma condição nomeada para a desfazer: **existir
    um consumidor da outbox**. A razão era que, sem consumidor nem `beat`,
    escrever na outbox significava que a rasterização e a extração nunca
    corriam.

    A condição cumpriu-se — `apps/shared/consumidor.py` e a entrada de
    `CELERY_BEAT_SCHEDULE` — e a divergência está desfeita. O que a motivou
    também cobrou o preço entretanto, e é a razão de isto ter deixado de ser
    adiável: um worker com uma imagem de sete dias recebeu as duas tarefas que
    esta função enfileirava e respondeu `Received unregistered task ... The
    message has been ignored and discarded`. Fila a zero, nenhum rasto na
    aplicação, documento preso em `a_normalizar`. Com a outbox, o mesmo worker
    velho deixa a linha pendente, com `attempts`, `last_error` e `processed_at`
    nulo — o atraso passa a ser uma linha que se consulta.

    ## O que esta função deixou de ter de fazer

    Dois mecanismos desapareceram daqui, os dois por o handler correr **dentro**
    do âmbito do tenant:

    * a leitura das páginas antes do `on_commit`. Era obrigatória e tinha sido um
      defeito a sério: a closure de um `on_commit` corre fora do `tenant_scope`,
      onde a política devolve zero linhas sem erro, pelo que a lista vinha vazia
      e nada era enfileirado — em produção, *"a imagem nunca fica pronta"*, sem
      uma linha de log. Quem o apanhou foi o guarda de âmbito do
      `tests/conftest.py`. O handler lê as páginas ele mesmo, com âmbito aberto;
    * a chamada ao `pedir` do porto da extração. O porto existia por o
      `purchasing` não poder importar o `agents`; o evento resolve a mesma coisa
      sem porto nenhum, que é o que o topo do `apps/purchasing/extracao.py` já
      dizia ser o mecanismo certo. A metade `leituras` do porto fica.

    Devolve a linha da outbox, que é o que torna o enfileiramento **observável**
    num teste sem espiar o broker.
    """
    return publish(DocumentoFechado(tenant_id=tenant_id, documento_id=documento_id))


@transaction.atomic
def criar_documento(
    *,
    tenant_id: UUID,
    created_by_id: UUID | None,
    created_by_name: str,
    ficheiro: FicheiroRecebido | None = None,
) -> InvoiceDocument:
    """Cria o documento. Com ficheiro é um upload; sem ficheiro é um slot.

    ## A origem é **derivada** e não declarada

    Um pedido que traz ficheiro é `upload`; um pedido vazio é o slot que o QR
    nomeia, logo `capture`. A ADR não diz quem escreve a coluna `source`, e esta
    é a leitura que não acrescenta um parâmetro que o cliente possa pôr errado —
    pela mesma lógica com que o `content_type` do cliente é ignorado: o que vale é
    o que aconteceu, não o que o pedido afirma.

    O preço está nomeado: um desktop que abra um slot e depois lhe envie
    ficheiros fica marcado como `capture`. É a leitura certa do que aconteceu (o
    slot foi aberto para captura) mas não é a única possível, e é uma das coisas
    que o dono pode querer rever.

    ## E a origem decide quem fecha

    *"Um ficheiro fecha-se a si mesmo (um PDF de dez páginas é um documento
    completo e o número de páginas sabe-se do ficheiro); uma captura é fechada
    por uma pessoa"* (ADR 0021, decisão 9). Logo um `upload` nasce **fechado** e
    com o trabalho já agendado; um `capture` nasce aberto e espera pelo
    `closing`.
    """
    origem = OrigemDoDocumento.UPLOAD if ficheiro is not None else OrigemDoDocumento.CAPTURE
    documento = InvoiceDocument.objects.create(
        tenant_id=tenant_id,
        source=origem,
        created_by_id=created_by_id,
        created_by_name=created_by_name,
    )
    if ficheiro is None:
        return documento

    _guardar_ficheiro(tenant_id=tenant_id, documento=documento, recebido=ficheiro)
    documento.closed_at = timezone.now()
    documento.save(update_fields=["closed_at", "updated_at"])
    enfileirar_trabalho_do_documento(tenant_id=tenant_id, documento_id=documento.id)
    return documento


@transaction.atomic
def anexar_ficheiro(
    *, tenant_id: UUID, documento: InvoiceDocument, ficheiro: FicheiroRecebido
) -> bool:
    """Anexa um ficheiro ao documento. Devolve se ele era **novo**.

    `False` é a retentativa: os mesmos bytes já estão neste documento, não se
    cria um segundo ficheiro nem uma segunda página, e quem chamou fica a saber
    (a view responde 200 em vez de 201). É a idempotência observável que a ADR
    0021 pede no desvio 5, aplicada à escrita que mais sofre com uma rede má — a
    de um telemóvel a enviar uma fotografia.

    O estado do documento é relido **sob o lock** e não da instância que a view
    carregou: entre o `get_object()` e esta linha o documento pode ter sido
    fechado por outro pedido, e aceitar uma página num documento já fechado é
    aceitar uma folha numa fatura que já foi para extração.
    """
    bloqueado = _bloquear(tenant_id=tenant_id, documento_id=documento.id)
    _exigir_aberto(bloqueado)
    return _guardar_ficheiro(tenant_id=tenant_id, documento=bloqueado, recebido=ficheiro)


@transaction.atomic
def fechar_documento(*, tenant_id: UUID, documento: InvoiceDocument) -> InvoiceDocument:
    """Fecha o documento: não vêm mais páginas. **Repetível.**

    Repetível de propósito (ADR 0020, decisão 1g): uma retentativa numa rede má
    devolve 200 em vez de uma recusa sobre uma operação que afinal correu bem.
    Fechar duas vezes não compra nada a ninguém, e o segundo fecho não volta a
    agendar trabalho — senão um duplo toque pagava duas extrações. E é o **lock**
    que o garante e não o `if`: dois pedidos simultâneos a ver `closed_at IS
    NULL` fechavam os dois e pediam duas extrações, que é dinheiro a dobrar pelo
    mesmo documento.
    """
    bloqueado = _bloquear(tenant_id=tenant_id, documento_id=documento.id)
    if bloqueado.discarded_at is not None:
        raise RecusaDeDocumento(CODIGO_DOCUMENTO_DESCARTADO, DETALHE_DOCUMENTO_DESCARTADO)
    if bloqueado.closed_at is not None:
        return bloqueado
    if not bloqueado.pages.exists():
        raise RecusaDeDocumento(
            CODIGO_DOCUMENTO_SEM_PAGINAS, DETALHE_DOCUMENTO_SEM_PAGINAS
        )
    bloqueado.closed_at = timezone.now()
    bloqueado.save(update_fields=["closed_at", "updated_at"])
    enfileirar_trabalho_do_documento(tenant_id=tenant_id, documento_id=bloqueado.id)
    return bloqueado


@transaction.atomic
def descartar_documento(*, tenant_id: UUID, documento: InvoiceDocument) -> None:
    """Descarta o documento. **Só apaga bytes se não houver páginas.**

    É a decisão 9 da ADR 0021 à letra, e a razão de ela não ser simétrica: um
    documento sem páginas é um slot que ninguém usou e os seus bytes (se houver)
    não são prova de nada; um documento **com** páginas pode já ter sido lido por
    uma pessoa, e apagar a imagem de uma fatura é apagar o original de um
    documento fiscal — que é exactamente a segunda pergunta que o dono ainda não
    respondeu ("depois de lançar a fatura, o que faz com o papel? e o
    contabilista precisa do ficheiro?"). Sem resposta, não se apaga.

    Repetível: descartar um documento já descartado não escreve nada e não
    levanta. É a mesma razão do fecho — um duplo toque não é um erro —, e é o
    lock que a torna verdadeira em dois pedidos simultâneos.
    """
    bloqueado = _bloquear(tenant_id=tenant_id, documento_id=documento.id)
    if bloqueado.discarded_at is not None:
        return
    bloqueado.discarded_at = timezone.now()
    bloqueado.save(update_fields=["discarded_at", "updated_at"])
    if bloqueado.pages.exists():
        return
    for caminho in bloqueado.files.values_list("path", flat=True):
        _apagar_bytes(caminho)
    bloqueado.files.all().delete()


@transaction.atomic
def registar_normalizacao(
    *, tenant_id: UUID, pagina_id: UUID, imagem: ImagemNormalizada
) -> bool:
    """Guarda a imagem normalizada de uma página e marca-a como pronta.

    Chamada **só** pela tarefa `normalizar_pagina`, depois de a fronteira da
    rasterização ter devolvido bytes. Devolve `False` se a página já não existe
    (foi descartada entre o enfileiramento e a execução), que é o caso normal de
    uma tarefa a correr tarde e não um erro.

    A ordem é: escrever os bytes, depois a linha. O contrário deixava uma página
    marcada como normalizada a apontar para um ficheiro que ainda não existe, e é
    nessa janela que o ecrã de revisão pede a imagem.
    """
    pagina = DocumentPage.objects.filter(tenant_id=tenant_id, pk=pagina_id).first()
    if pagina is None:
        return False
    caminho = caminho_da_imagem(
        tenant_id=tenant_id, documento_id=pagina.document_id, pagina_id=pagina.id
    )
    _escrever_bytes(caminho, imagem.webp)
    pagina.image_path = caminho
    pagina.width = imagem.width
    pagina.height = imagem.height
    pagina.normalized_at = timezone.now()
    pagina.save(
        update_fields=["image_path", "width", "height", "normalized_at", "updated_at"]
    )
    return True


@transaction.atomic
def limpar_slots_expirados(*, tenant_id: UUID, agora: datetime | None = None) -> int:
    """Apaga os slots que nunca receberam página e já passaram do relógio.

    Devolve quantos apagou. Um slot vazio e expirado é uma intenção que não se
    concretizou — não aparece na lista (é o `selectors.documentos_visiveis` que o
    filtra) e não tem bytes, porque sem página nenhuma nunca houve ficheiro
    aceite. Apagar é a limpeza que a ADR 0020 prometeu à decisão 2.

    **Continua a não correr**, e já não é por falta de `beat` — esse existe desde
    2026-10-08. É porque ela é por tenant e o cron que iteraria os
    estabelecimentos teria de ler o `accounts_tenant`, que dentro de
    `system_scope()` devolve zero linhas sem erro: a política dele não tem o
    disjunto `app.scope`. A razão por extenso, e as duas saídas possíveis, estão
    no topo do `apps/purchasing/tasks.py`.
    """
    agora = agora or timezone.now()
    ids = list(
        slots_expirados(tenant_id=tenant_id, limite=agora - JANELA_DO_SLOT).values_list(
            "id", flat=True
        )
    )
    if not ids:
        return 0
    # Os ficheiros de um slot vazio: só existem se um upload tiver criado a linha
    # do ficheiro e falhado antes da página, o que é uma transação revertida.
    # Apaga-se por segurança, e não por se esperar que aconteça.
    for caminho in DocumentFile.objects.filter(
        tenant_id=tenant_id, document_id__in=ids
    ).values_list("path", flat=True):
        _apagar_bytes(caminho)
    # `id__in` de uma lista e não `queryset.delete()` do selector: o selector traz
    # um `annotate(Count(...))`, e o `delete()` do Django não aceita uma queryset
    # com agregação. A lista é curta por construção — são slots de 15 minutos.
    InvoiceDocument.objects.filter(tenant_id=tenant_id, id__in=ids).delete()
    logger.info("slots expirados apagados", extra={"event": "slot.purga", "count": len(ids)})
    return len(ids)


# ---------------------------------------------------------------------------
# Privado
# ---------------------------------------------------------------------------
def _bloquear(*, tenant_id: UUID, documento_id: UUID) -> InvoiceDocument:
    """A linha do documento, relida e **trancada** até ao fim da transação.

    Um `SELECT ... FOR UPDATE` de uma linha, e é o que serializa as escritas ao
    **mesmo** documento. Não é zelo: a ADR 0020 prevê por extenso *"dois
    telemóveis a fotografar um rolo de cinco folhas"* a cair no mesmo documento,
    e sem o lock há três corridas reais:

    1. **as posições.** A posição de um ficheiro e de uma página é
       `count() + 1`; dois pedidos simultâneos calculam o mesmo número e o
       segundo viola a unicidade — o que, sem lock, aparecia como um 500 ou
       (pior) como um "ficheiro duplicado" numa página que não era duplicada;
    2. **o fecho.** Dois `closing` ao mesmo tempo passavam os dois pelo
       `closed_at IS NULL` e pediam **duas** extrações, que é dinheiro a dobrar;
    3. **o estado lido pela view.** O `get_object()` leu a linha antes das
       permissões; aceitar uma página com base nesse valor é aceitar uma folha
       num documento que foi fechado entretanto.

    O preço é nomeado: o lock é mantido enquanto os bytes são escritos no disco
    (até 12 MiB), e trava **só** outras escritas ao mesmo documento. É a troca
    certa — a alternativa era resolver três corridas com três retentativas.

    Levanta `RecusaDeDocumento` se a linha já não existir: a única coisa que
    apaga um documento é a tarefa de limpeza dos slots vazios, e um pedido que
    chegue depois dela não tem onde escrever.
    """
    documento = (
        InvoiceDocument.objects.select_for_update()
        .filter(tenant_id=tenant_id, pk=documento_id)
        .first()
    )
    if documento is None:
        raise RecusaDeDocumento(CODIGO_DOCUMENTO_DESCARTADO, DETALHE_DOCUMENTO_DESCARTADO)
    return documento


def _exigir_aberto(documento: InvoiceDocument) -> None:
    """Recusa escrever num documento fechado ou descartado."""
    if documento.discarded_at is not None:
        raise RecusaDeDocumento(CODIGO_DOCUMENTO_DESCARTADO, DETALHE_DOCUMENTO_DESCARTADO)
    if documento.closed_at is not None:
        raise RecusaDeDocumento(CODIGO_DOCUMENTO_FECHADO, DETALHE_DOCUMENTO_FECHADO)


def _guardar_ficheiro(
    *, tenant_id: UUID, documento: InvoiceDocument, recebido: FicheiroRecebido
) -> bool:
    """Escreve a linha do ficheiro, as linhas das páginas e os bytes.

    Devolve `False` quando os mesmos bytes já estavam neste documento. A ordem é
    deliberada: calcula-se o digest primeiro (uma passagem pelo ficheiro, sem o
    trazer todo para memória), consulta-se a unicidade, e só depois se escreve —
    uma retentativa não deixa um segundo ficheiro no disco antes de a recusa
    acontecer.

    Quem chama tem o documento **trancado** (`_bloquear`), logo as posições e a
    unicidade não têm corrida. O `except IntegrityError` fica como segunda rede,
    e é o que apanha uma escrita que chegue por um caminho que esqueça o lock: a
    constraint `documentfile_document_sha256_uniq` é a regra, e o `if` acima é só
    a forma de responder 200 em vez de 500 no caso normal.
    """
    digest = _digest(recebido.ficheiro)
    if DocumentFile.objects.filter(
        tenant_id=tenant_id, document=documento, sha256=digest
    ).exists():
        return False

    _exigir_cabida(documento=documento, quantas=recebido.paginas)

    posicao = (
        DocumentFile.objects.filter(tenant_id=tenant_id, document=documento).count() + 1
    )
    caminho = caminho_do_ficheiro(
        tenant_id=tenant_id, documento_id=documento.id, tipo=recebido.tipo
    )
    try:
        with transaction.atomic():
            linha = DocumentFile.objects.create(
                tenant_id=tenant_id,
                document=documento,
                position=posicao,
                path=caminho,
                original_filename=recebido.original_filename,
                content_type=recebido.tipo,
                byte_size=recebido.byte_size,
                sha256=digest,
                pages_detected=recebido.paginas,
            )
    except IntegrityError:
        # A outra metade da corrida ganhou. Não é erro: o ficheiro está lá.
        logger.info(
            "ficheiro duplicado recusado pela constraint",
            extra={"event": "documento.ficheiro", "outcome": "duplicado"},
        )
        return False

    primeira = (
        DocumentPage.objects.filter(tenant_id=tenant_id, document=documento).count() + 1
    )
    DocumentPage.objects.bulk_create(
        [
            DocumentPage(
                tenant_id=tenant_id,
                document=documento,
                file=linha,
                file_page_number=numero,
                position=primeira + numero - 1,
            )
            for numero in range(1, recebido.paginas + 1)
        ]
    )
    _escrever_ficheiro(caminho, recebido.ficheiro)
    return True


def _exigir_cabida(*, documento: InvoiceDocument, quantas: int) -> None:
    """O teto de páginas por documento, contado com as que já lá estão."""
    ja_tem = documento.pages.count()
    if ja_tem + quantas > PAGINAS_POR_DOCUMENTO:
        raise RecusaDeDocumento(
            CODIGO_PAGINAS_EXCEDIDAS,
            DETALHE_PAGINAS_EXCEDIDAS.format(limite=PAGINAS_POR_DOCUMENTO),
        )


def _digest(ficheiro) -> str:
    """O SHA-256 dos bytes, por blocos, com o ficheiro rebobinado no fim."""
    ficheiro.seek(0)
    soma = hashlib.sha256()
    for bloco in iter(lambda: ficheiro.read(BLOCO), b""):
        soma.update(bloco)
    ficheiro.seek(0)
    return soma.hexdigest()


def _escrever_ficheiro(relativo: str, ficheiro) -> None:
    """Escreve o upload no `MEDIA_ROOT`, por blocos."""
    destino = caminho_dentro_do_media(relativo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    ficheiro.seek(0)
    with destino.open("wb") as saida:
        for bloco in iter(lambda: ficheiro.read(BLOCO), b""):
            saida.write(bloco)


def _escrever_bytes(relativo: str, dados: bytes) -> None:
    """Escreve bytes já em memória (a imagem normalizada) no `MEDIA_ROOT`."""
    destino = caminho_dentro_do_media(relativo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(dados)


def _apagar_bytes(relativo: str) -> None:
    """Apaga um ficheiro do `MEDIA_ROOT`, se lá estiver.

    `missing_ok`: um ficheiro que já não existe não é erro — é o estado que se
    quer. Um `FileNotFoundError` aqui transformava uma limpeza numa falha.
    """
    caminho_dentro_do_media(relativo).unlink(missing_ok=True)


# ============================================================================
# Receção de mercadoria (fatia 2, parte B)
# ============================================================================


class CriacaoDeRececaoJaExiste(Exception):
    """Receção já existe para este documento."""

    def __init__(self, receipt_id: UUID):
        self.receipt_id = receipt_id
        super().__init__()


class RececaoConfirmada(Exception):
    """Receção já foi confirmada."""

    pass


class SemLinhasRevistas(Exception):
    """Receção não tem linhas revistas para confirmar."""

    pass


class LocalizacaoInativa(Exception):
    """Localização não está ativa."""

    pass


class ArtigoInativo(Exception):
    """Artigo não está ativo."""

    pass


class ConversaoEmFalta(Exception):
    """Não conseguiu converter a unidade de fatura."""

    pass


class SemArtigo(Exception):
    """Linha de goods sem artigo."""

    pass


class LoteObrigatorio(Exception):
    """Artigo com track_lots precisa de lote."""

    pass


class ValidadeObrigatoria(Exception):
    """Artigo com expiry_kind precisa de validade."""

    pass


def criar_rececao(
    *,
    tenant_id: UUID,
    location_id: UUID,
    document_id: UUID | None = None,
    supplier_name: str = "",
    supplier_nif: str | None = None,
    doc_number: str | None = None,
    doc_date = None,
    customer_name: str = "",
    customer_nif: str = "",
    document_total_eur: Decimal | None = None,
    supplier_id: UUID | None = None,
    doc_type: str = "",
    received_at = None,
) -> Receipt:
    """Cria uma receção, opcionalmente semeada com linhas de um documento.

    Repetição com o mesmo `document` devolve 200 com a receção existente.
    """
    with transaction.atomic():
        # Verificar se já existe receção para este documento
        if document_id:
            try:
                existing = Receipt.objects.get(tenant_id=tenant_id, document_id=document_id)
                raise CriacaoDeRececaoJaExiste(existing.id)
            except Receipt.DoesNotExist:
                pass

        # Criar receção
        received_at = received_at or timezone.now()

        receipt = Receipt.objects.create(
            tenant_id=tenant_id,
            document_id=document_id,
            supplier_name=supplier_name,
            supplier_nif=supplier_nif or "",
            doc_number=doc_number or "",
            doc_date=doc_date,
            customer_name=customer_name,
            customer_nif=customer_nif,
            document_total_eur=document_total_eur,
            supplier_id=supplier_id,
            doc_type=doc_type,
            received_at=received_at,
            location_id=location_id,
        )

        return receipt


def rever_linha(
    *,
    receipt_id: UUID,
    linha_id: UUID,
    product_id: UUID | None = None,
    packaging_id: UUID | None = None,
    base_per_invoice_unit: Decimal | None = None,
    quantity_received: Decimal | None = None,
    location_id: UUID | None = None,
    kind: str = "goods",
    lot_code: str = "",
    expires_at = None,
    skip: bool = False,
    reviewed_by_id: UUID | None = None,
    reviewed_by_name: str = "",
) -> ReceiptLine:
    """Revê uma linha de receção."""
    with transaction.atomic():
        receipt = Receipt.objects.get(pk=receipt_id)

        if receipt.confirmed_at:
            raise RececaoConfirmada()

        linha = ReceiptLine.objects.get(pk=linha_id, receipt_id=receipt_id)

        # Determinar o status
        status = "skipped" if skip else "needs_review"

        if kind == "goods":
            if not product_id:
                raise SemArtigo()

        # Atualizar a linha
        linha.product_id = product_id
        linha.packaging_id = packaging_id
        linha.base_per_invoice_unit = base_per_invoice_unit
        linha.quantity_received = quantity_received or linha.quantity_invoiced or Decimal(0)
        if location_id:
            linha.location_id = location_id
        linha.kind = kind
        linha.lot_code = lot_code.strip().upper() if lot_code else ""
        linha.expires_at = expires_at
        linha.status = status
        linha.reviewed_by_id = reviewed_by_id
        linha.reviewed_by_name = reviewed_by_name
        linha.reviewed_at = timezone.now()
        linha.save()

        return linha


def registar_temperatura(
    *,
    receipt_id: UUID,
    conservation: str,
    celsius: Decimal,
    measured_by_name: str,
    measured_at = None,
) -> Receipt:
    """Registra temperatura em receção."""
    measured_at = measured_at or timezone.now()

    receipt = Receipt.objects.get(pk=receipt_id)

    if conservation == "chilled":
        receipt.chilled_temperature_c = celsius
        receipt.chilled_measured_at = measured_at
        receipt.chilled_measured_by_name = measured_by_name
    elif conservation == "frozen":
        receipt.frozen_temperature_c = celsius
        receipt.frozen_measured_at = measured_at
        receipt.frozen_measured_by_name = measured_by_name

    receipt.save()
    return receipt


def confirmar_rececao(
    *,
    receipt_id: UUID,
    confirmed_by_id: UUID | None = None,
    confirmed_by_name: str = "",
) -> Receipt:
    """Confirma uma receção de mercadoria (fatia 3: escreve no ledger de stock).

    Executa de forma atómica:
    1. Se já confirmada, retorna o estado atual (idempotência).
    2. Se não há linhas revistas (confirmed/skipped), lança SemLinhasRevistas.
    3. Passa linhas needs_review restantes a skipped.
    4. Cria os lotes para as linhas confirmed (inventory_api.get_or_create_lots).
    5. Grava os movimentos de stock (inventory_api.record_movements).
    6. Preenche movement_id nas linhas confirmed (deduplicação por reference).
    7. Emite evento StockReceived na outbox.
    8. Memoriza correspondências do catálogo (catalog_api).
    """
    with transaction.atomic():
        receipt = _bloquear_rececao(receipt_id)

        # Se já confirmada, retorna como está (idempotência observável — 200)
        if receipt.confirmed_at:
            return receipt

        # Verificar se há linhas revistas
        linhas_revistas = receipt.lines.filter(
            status__in=["confirmed", "skipped"]
        ).count()

        if linhas_revistas == 0:
            raise SemLinhasRevistas()

        # Passar needs_review para skipped
        receipt.lines.filter(status="needs_review").update(
            status="skipped",
            reviewed_by_id=confirmed_by_id,
            reviewed_by_name=confirmed_by_name,
            reviewed_at=timezone.now(),
        )

        # Gerar referência e salvar confirmação
        doc_type = receipt.doc_type
        doc_number = receipt.doc_number or receipt.doc_number_normalized or ""
        reference = f"{doc_type} {doc_number}".strip()
        if not reference:
            reference = receipt.supplier_name or f"Receção {receipt.id}"

        receipt.reference = reference[:120]
        receipt.confirmed_at = timezone.now()
        receipt.confirmed_by_id = confirmed_by_id
        receipt.confirmed_by_name = confirmed_by_name
        receipt.save()

        # === Fatia 3: Escrever no ledger de stock ===
        linhas_confirmed = list(
            receipt.lines.filter(status="confirmed", product_id__isnull=False)
        )

        if linhas_confirmed:
            # 1. Criar lotes (se track_lots=True)
            lotes_a_criar = []
            for linha in linhas_confirmed:
                # expires_at é DateField na receção, mas Lot espera DateTime
                expires_dt = None
                if linha.expires_at:
                    expires_dt = datetime.combine(linha.expires_at, datetime.min.time())
                    expires_dt = timezone.make_aware(expires_dt)

                lotes_a_criar.append(
                    (
                        linha.product_id,
                        linha.lot_code or f"__{linha.product_id}__",  # Lote sintético se vazio
                        expires_dt,
                        receipt.received_at,  # received_at vem da receção
                    )
                )

            lotes_map = inventory_api.get_or_create_lots(
                tenant_id=receipt.tenant_id,
                items=lotes_a_criar,
            )

            # 2. Preparar movimentos
            movimentos_dtos = []
            for linha in linhas_confirmed:
                # unit_cost = line_total / quantity_received (ADR 0023, decisão 3)
                if linha.quantity_received and linha.line_total:
                    unit_cost = linha.line_total / linha.quantity_received
                else:
                    unit_cost = Decimal("0")

                lot_id = lotes_map.get(
                    (linha.product_id, linha.lot_code or f"__{linha.product_id}__")
                )

                # **Só a nota de crédito é devolução** (ADR 0023, decisão 2 e
                # cenários 1 e 6). Até 2026-10-16 lia-se `"receipt" if doc_type
                # == "FT" else "return"`, e com isso uma fatura-recibo, uma
                # fatura simplificada, uma guia de remessa e uma nota de débito
                # — todas entradas de mercadoria — entravam no ledger como
                # devoluções, com o sinal trocado em relação ao que a ADR 0014
                # diz que cada movimento significa para o dinheiro. A NC reduz,
                # e reduzir é a quantidade a negativo: o `return` com quantidade
                # positiva **aumentava** o stock que a nota de crédito tira.
                devolucao = receipt.doc_type == DOC_TIPO_QUE_SUBTRAI
                mvt_dto = inventory_api.MovementDTO(
                    product_id=linha.product_id,
                    location_id=linha.location_id,
                    lot_id=lot_id,
                    quantity=(
                        -linha.quantity_received if devolucao else linha.quantity_received
                    ),
                    unit_cost=unit_cost,
                    cost_is_estimate=False,  # Opção B da Q8: custo confirmado (não estimado)
                    movement_type="return" if devolucao else "receipt",
                    occurred_at=receipt.received_at,
                    created_by_id=confirmed_by_id,
                    created_by_name=confirmed_by_name,
                    reference=receipt.reference,
                    reason="",
                    production_id=None,
                )
                movimentos_dtos.append((linha, mvt_dto))

            # 3. Gravar movimentos (atomicamente)
            movement_ids = inventory_api.record_movements(
                tenant_id=receipt.tenant_id,
                movements=[mvt_dto for _, mvt_dto in movimentos_dtos],
            )

            # 4. Preencher movement_id nas linhas (mesma transação)
            # `strict`: o ledger devolve um id por DTO, pela ordem de entrada;
            # uma lista mais curta era uma linha sem movimento, em silêncio.
            for (linha, _), movimento_id in zip(movimentos_dtos, movement_ids, strict=True):
                linha.movement_id = movimento_id
                linha.save(update_fields=["movement_id", "updated_at"])

            # 5. Emitir evento StockReceived
            linhas_para_evento = [
                {
                    "product_id": str(linha.product_id),
                    "quantity": str(linha.quantity_received),
                    "unit_cost": str(linha.line_total / linha.quantity_received)
                    if linha.quantity_received and linha.line_total
                    else "0",
                }
                for linha in linhas_confirmed
            ]
            publish(
                StockReceived(
                    tenant_id=receipt.tenant_id,
                    receipt_id=receipt.id,
                    lines=linhas_para_evento,
                )
            )

        # Memorizar correspondências do catálogo
        if receipt.supplier_id:
            linhas_confirmed_goods = receipt.lines.filter(
                status="confirmed",
                kind="goods",
                product_id__isnull=False,
                supplier_code__gt="",
            ).values_list("supplier_code", "description", "product_id", "packaging_id")

            if linhas_confirmed_goods:
                correspondencias_aprendidas = [
                    catalog_api.CorrespondenciaAprendida(
                        code=row[0].strip().upper(),
                        description_raw=row[1],
                        product_id=row[2],
                        packaging_id=row[3],
                    )
                    for row in linhas_confirmed_goods
                ]

                catalog_api.memorizar_correspondencias(
                    tenant_id=receipt.tenant_id,
                    supplier_id=receipt.supplier_id,
                    itens=correspondencias_aprendidas,
                )

        return receipt


def _bloquear_rececao(receipt_id: UUID) -> Receipt:
    """Lock para evitar corridas na confirmação."""
    return Receipt.objects.select_for_update().get(pk=receipt_id)


def apagar_rascunho(*, receipt_id: UUID) -> None:
    """Apaga uma receção em status needs_review."""
    receipt = Receipt.objects.get(pk=receipt_id)

    if receipt.confirmed_at:
        raise RececaoConfirmada()

    # Disassociar documento
    if receipt.document_id:
        receipt.document = None
        receipt.save()

    # Apagar linhas
    receipt.lines.all().delete()

    # Apagar receção
    receipt.delete()
