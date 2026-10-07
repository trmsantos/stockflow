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
from uuid import UUID

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.purchasing.extracao import fronteira_da_extracao
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
)
from apps.purchasing.rasterizacao import ImagemNormalizada
from apps.purchasing.selectors import slots_expirados

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


def enfileirar_trabalho_do_documento(*, tenant_id: UUID, documento_id: UUID) -> None:
    """O **único** ponto onde o trabalho de um documento é agendado.

    Duas coisas, nesta ordem e as duas depois do commit: rasterizar as páginas
    que ainda não têm imagem, e pedir a extração.

    ## Porque é que isto não escreve na outbox

    O `CLAUDE.md` diz *"efeitos secundários em Celery via outbox"*, e esta função
    usa `transaction.on_commit` + `.delay()` em vez disso. **A divergência é
    deliberada e está decidida por quem manda nesta feature**: não há consumidor
    da outbox nem `beat` neste repositório (ADR 0010, ADR 0020, ADR 0021), logo
    escrever na outbox hoje significa que a rasterização e a extração **nunca
    correm** — o evento ficaria numa tabela à espera de um worker que não existe,
    e a fatia 1 entregaria um documento que nunca é lido.

    **A condição exacta para trocar:** existir um consumidor da outbox. Nesse dia
    isto passa a `publish(DocumentoFechado(...))` e as duas tarefas são
    enfileiradas pelos `handlers.py` dos módulos respectivos — o que resolve de
    caminho a razão pela qual a extração é pedida através de um porto
    (`extracao.py`) em vez de um import.

    O `on_commit` **não** é opcional: enfileirar antes do commit publica um facto
    que pode desaparecer, e a tarefa corre contra uma linha que não existe — é o
    modo de falha que a própria outbox existe para evitar, e é a metade da regra
    que esta função mantém.
    """
    # Import no corpo e não no topo: o `tasks.py` importa este módulo (os
    # serviços são a única forma de escrever), logo um import no topo era um
    # ciclo. É o mesmo padrão do `semear_demonstracao` no `accounts/api.py`, e
    # sem supressão de lint nenhuma.
    from apps.purchasing.tasks import normalizar_pagina

    # **A leitura é aqui e não dentro do `_agendar`**, e isto foi um defeito a
    # sério: um `on_commit` corre *depois* de a transação fechar, logo **fora** do
    # `tenant_scope` — e lá a política devolve zero linhas sem erro, pelo que a
    # lista de páginas vinha vazia e nenhuma rasterização era enfileirada. Em
    # produção isso aparecia como "a imagem nunca fica pronta", sem erro nenhum
    # no log. Quem o apanhou foi o guarda de âmbito do `tests/conftest.py`, que é
    # exactamente a classe de defeito que ele existe para apanhar.
    paginas = list(
        DocumentPage.objects.filter(
            tenant_id=tenant_id, document_id=documento_id, normalized_at__isnull=True
        ).values_list("id", flat=True)
    )

    def _agendar() -> None:
        for pagina_id in paginas:
            normalizar_pagina.delay(tenant_id=str(tenant_id), pagina_id=str(pagina_id))

    transaction.on_commit(_agendar)
    fronteira = fronteira_da_extracao()
    if fronteira is not None:
        # O `pedir` do porto é que faz o seu próprio `on_commit` — é o contrato
        # declarado em `extracao.py`, e deixá-lo a ele mantém a regra num sítio
        # por aresta em vez de a embrulhar duas vezes.
        fronteira.pedir(tenant_id=tenant_id, documento_id=documento_id)


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

    **Não corre hoje**: não há `beat` neste projecto, e esta feature é a primeira
    a precisar dele — dívida já nomeada no `SESSION-CONTEXT.md` e repetida na
    ADR 0021. A função existe, é testável, e o dia em que o `beat` existir é uma
    entrada de configuração e não código novo.
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
