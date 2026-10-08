"""O contrato HTTP de `/api/v1/documents` (ADR 0021, decisão 9).

Leitura e escrita em classes separadas, e os campos listados um a um — nunca
`fields = "__all__"` (CLAUDE.md, SECURITY.md §4). Aqui a separação sai de graça:
**nenhum destes serializers é um `ModelSerializer`**. Os de escrita recebem um
ficheiro e mais nada; os de leitura serializam o `DocumentoCompleto` do
`selectors.py` e os DTO congelados do `extracao.py`, com **todos** os campos
declarados à mão. Não há, portanto, nenhum caminho por onde uma coluna nova de um
modelo apareça sozinha numa resposta — o `path` do ficheiro no disco e o
`created_by` (o uuid da conta) não estão na lista e não podem passar a estar por
acidente.

É também a convenção do `apps/accounts/serializers.py`, que é o único precedente
deste repositório: `XInSerializer` e `XOutSerializer`. O instinto de os chamar
`XRead`/`XCreate`/`XUpdate` perde contra a consistência com o módulo vizinho —
quem lê a API lê os dois ficheiros.

## Os nomes dos campos são ingleses, e é uma decisão da ADR

*"Caminhos e campos em inglês, como os vizinhos"* (ADR 0021, decisão 9). A
excepção do `accounts` — onde o topo do contrato está em português por força da
ADR 0010 — não se estende aqui: estes campos espelham colunas de modelos
(`closed_at`, `page_count`, `original_filename`), e é a fronteira do módulo que
separa as duas convenções.

## Onde é que a validação do ficheiro vive, e porquê aqui

O serializer é a fronteira (SECURITY.md §4), e é aqui que se recusa por campo:
tamanho, bytes mágicos, ficheiro vazio, PDF com páginas a mais. O serviço não
revalida — recebe um `FicheiroRecebido`, que é uma classe que só existe depois de
isto ter corrido. O que **não** acontece aqui é abrir o ficheiro com um decoder:
nenhum decoder nativo corre no processo que serve pedidos (ADR 0020, decisão 4), e
tudo o que este módulo faz aos bytes é comparar prefixos e contar um token.
"""

from __future__ import annotations

from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.purchasing.ficheiros import (
    BYTES_PARA_DECIDIR,
    TAMANHO_MAXIMO_DO_FICHEIRO,
    paginas_num_pdf,
    tipo_real,
)
from apps.purchasing.models import (
    PAGINAS_POR_DOCUMENTO,
    EstadoDaLeitura,
    EstadoDoDocumento,
    OrigemDoDocumento,
)
from apps.purchasing.services import FicheiroRecebido

__all__ = [
    "DocumentoInSerializer",
    "DocumentoOutSerializer",
    "ExtracaoOutSerializer",
    "FicheiroDeDocumentoInSerializer",
    "FicheiroOutSerializer",
    "LinhaLidaOutSerializer",
    "PaginaOutSerializer",
    "RecusaDeDocumentoOutSerializer",
]

#: O tipo que o cliente declara é **ignorado**, e a frase que ele recebe diz o
#: que se aceita de facto: os três formatos cuja assinatura este projecto
#: reconhece. Uma frase que dissesse "tipo inválido" mandava a pessoa adivinhar.
DETALHE_TIPO_RECUSADO = _(
    "Only a PDF, a JPEG or a PNG. What decides is the content of the file and "
    "never its name or the declared type."
)
DETALHE_FICHEIRO_VAZIO = _("This file has no content.")
DETALHE_FICHEIRO_GRANDE = _("This file is larger than {limite} MiB.")
DETALHE_PDF_COM_PAGINAS_A_MAIS = _(
    "This PDF has {paginas} pages and a document takes at most {limite}."
)


def _validar(ficheiro: UploadedFile) -> FicheiroRecebido:
    """Recusa por campo, e devolve o que o serviço precisa. Nesta ordem.

    A ordem não é arbitrária e cada passo tem um porquê:

    1. **tamanho primeiro**, pelo `size` que o parser já sabe. É o único que se
       decide sem ler um byte, e ler 13 MiB para depois os recusar é o trabalho
       que o teto existe para evitar;
    2. **os bytes mágicos**, sobre os primeiros bytes e não sobre o ficheiro
       todo;
    3. **as páginas**, e só para um PDF — uma imagem é uma página por definição.
       Aqui o ficheiro é lido por inteiro (está limitado a 12 MiB pelo passo 1),
       porque o contador procura um token que pode estar em qualquer sítio.

    O ficheiro fica **rebobinado** no fim: quem o lê a seguir é o serviço, para o
    digest e para o disco, e um ficheiro meio lido escreveria metade.
    """
    if ficheiro.size is None or ficheiro.size == 0:
        raise serializers.ValidationError(DETALHE_FICHEIRO_VAZIO)
    if ficheiro.size > TAMANHO_MAXIMO_DO_FICHEIRO:
        raise serializers.ValidationError(
            DETALHE_FICHEIRO_GRANDE.format(limite=TAMANHO_MAXIMO_DO_FICHEIRO // (1024 * 1024))
        )

    ficheiro.seek(0)
    tipo = tipo_real(ficheiro.read(BYTES_PARA_DECIDIR))
    if tipo is None:
        raise serializers.ValidationError(DETALHE_TIPO_RECUSADO)

    paginas = 1
    if tipo == "application/pdf":
        ficheiro.seek(0)
        paginas = paginas_num_pdf(ficheiro.read())
        if paginas > PAGINAS_POR_DOCUMENTO:
            raise serializers.ValidationError(
                DETALHE_PDF_COM_PAGINAS_A_MAIS.format(
                    paginas=paginas, limite=PAGINAS_POR_DOCUMENTO
                )
            )
    ficheiro.seek(0)
    return FicheiroRecebido(
        ficheiro=ficheiro,
        tipo=tipo,
        # O nome do cliente é um **rótulo**: entra numa coluna e nunca num
        # caminho (o caminho é gerado pelo `ficheiros.py`). O corte em 255 é o da
        # coluna, e é aqui para a recusa não vir do Postgres.
        original_filename=(ficheiro.name or "")[:255],
        byte_size=ficheiro.size,
        paginas=paginas,
    )


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
class DocumentoInSerializer(serializers.Serializer):
    """O corpo do `POST /documents`: um ficheiro, ou nada.

    **Nada** é o slot que o QR nomeia (ADR 0020, decisão 2): o desktop cria o
    documento vazio, o telemóvel anexa-lhe páginas. **Um ficheiro** é o upload de
    um só gesto, que é o que o dono pediu para o desktop.

    `source` não está aqui de propósito: a origem é derivada de vir ou não
    ficheiro (ver `services.criar_documento`), e um campo que o cliente
    declarasse era mais uma coisa que ele pode pôr errada.
    """

    #: `allow_empty_file=True` e a recusa do ficheiro vazio feita por nós: com o
    #: default do DRF a mensagem vinha dele, e as quatro recusas deste campo
    #: ficavam com três donos. Um ficheiro de zero bytes é recusado em
    #: `_validar`, com uma frase nossa e um teste.
    ficheiro = serializers.FileField(required=False, allow_empty_file=True)

    def validate_ficheiro(self, valor: UploadedFile) -> FicheiroRecebido:
        return _validar(valor)


class FicheiroDeDocumentoInSerializer(serializers.Serializer):
    """O corpo do `POST /documents/<id>/files`: **um** ficheiro, obrigatório.

    Um e não uma lista: *"um ficheiro é um documento, com N páginas, e nunca é
    partido automaticamente"* (ADR 0020, decisão 5), e duas fotografias são dois
    pedidos — o que é também o que faz uma retentativa de rede má poder ser
    idempotente por `sha256`, que uma lista parcialmente aceite não poderia.
    """

    #: `allow_empty_file=True` pela razão escrita no `DocumentoInSerializer`.
    ficheiro = serializers.FileField(allow_empty_file=True)

    def validate_ficheiro(self, valor: UploadedFile) -> FicheiroRecebido:
        return _validar(valor)


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
class PaginaOutSerializer(serializers.Serializer):
    """Uma página: a ordem, a imagem e a geometria.

    `image_url` é **sempre** servido, mesmo quando não há imagem, e quem decide
    se vale a pena pedi-lo é o `normalized`. A alternativa — um `image_url` nulo
    — dava ao cliente dois campos para a mesma pergunta e um tipo
    `string | null` para um caminho que nunca muda.

    Não sai o `id` da página: o endereço dela é `(documento, position)`, que é o
    que o path usa, e um segundo identificador no payload era mais uma coisa para
    o cliente escolher mal.
    """

    #: Os dois últimos são propriedades do modelo e aqui são só o tipo. Um
    #: `SerializerMethodField` para a mesma coisa sairia **opcional** no
    #: componente de resposta (`COMPONENT_NO_READ_ONLY_REQUIRED`), e o `types.ts`
    #: prometia `image_url?: string` num campo que o servidor manda sempre.
    position = serializers.IntegerField()
    image_url = serializers.CharField()
    width = serializers.IntegerField(allow_null=True)
    height = serializers.IntegerField(allow_null=True)
    normalized = serializers.BooleanField()


class FicheiroOutSerializer(serializers.Serializer):
    """Um ficheiro: o que entrou, quando, e o que os bytes diziam.

    `content_type` é o **real** (bytes mágicos) e não o que o cliente declarou —
    é a única forma deste campo, e é também o que o torna útil num relatório de
    suporte. `received_at` é o `created_at` da linha: a mesma coisa com o nome que
    o contrato lhe dá.

    Não sai o `path`: é um caminho no armazenamento do servidor, não tem valor
    nenhum para o cliente, e um payload que o traga é um payload que ensina a
    estrutura do disco a quem o ler.
    """

    position = serializers.IntegerField()
    original_filename = serializers.CharField(max_length=255, allow_blank=True)
    content_type = serializers.CharField(max_length=100)
    byte_size = serializers.IntegerField()
    pages_detected = serializers.IntegerField()
    received_at = serializers.DateTimeField(source="created_at")


class LinhaLidaOutSerializer(serializers.Serializer):
    """Uma linha **como o modelo a leu**. Texto não confiável, já validado.

    Chega aqui depois de o `agents` a ter validado contra o seu schema à escrita
    **e** à leitura (ADR 0021, decisão 4: *"é a única coluna do sistema em que
    nada se confia"*). O que este serializer acrescenta é a terceira passagem, a
    da forma do contrato: os `max_length` e os `decimal_places` são os que o
    `types.ts` vai prometer ao frontend.

    Os números são `Decimal` com `coerce_to_string` implícito (o default do DRF):
    saem como string no JSON, que é a única forma de um preço não passar por um
    `float` do JavaScript.
    """

    position = serializers.IntegerField()
    description = serializers.CharField(max_length=500, allow_blank=True)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, allow_null=True)
    unit = serializers.CharField(max_length=20, allow_blank=True)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=4, allow_null=True)
    vat_rate = serializers.DecimalField(max_digits=6, decimal_places=3, allow_null=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    confidence = serializers.DecimalField(max_digits=4, decimal_places=3, allow_null=True)


class ExtracaoOutSerializer(serializers.Serializer):
    """O que o modelo leu, num painel **só de leitura**.

    É a entrega da fatia 1 ao dono: *"arrastar um PDF no desktop, ver as páginas,
    e ver o que o modelo leu"*. Nada disto é a verdade do estabelecimento — a
    verdade é o que uma pessoa confirmar na revisão, que é a fatia 2 — e por isso
    o cabeçalho e as linhas vêm **vazios** quando o estado não é `lido`.

    `reason` é a razão legível de um `erro`, e existe porque hoje o erro é sempre
    o mesmo e tem uma explicação curta: não há modelo configurado. Um estado
    `erro` sem frase mandava alguém ler logs do worker. **Não está no
    `ExtracaoOut` da ADR** — é um campo aditivo, e o nome vai em inglês como os
    vizinhos (decisão 9), apesar de o campo do DTO interno se chamar `motivo`
    como o resto do Python deste repositório.
    """

    state = serializers.ChoiceField(choices=EstadoDaLeitura.choices)
    confidence = serializers.DecimalField(
        max_digits=4, decimal_places=3, allow_null=True
    )
    read_at = serializers.DateTimeField(allow_null=True)
    reason = serializers.CharField(source="motivo", allow_blank=True)
    supplier_name = serializers.CharField(max_length=200, allow_blank=True)
    supplier_nif = serializers.CharField(max_length=20, allow_blank=True)
    doc_type = serializers.CharField(max_length=20, allow_blank=True)
    doc_number = serializers.CharField(max_length=100, allow_blank=True)
    issued_at = serializers.DateField(allow_null=True)
    customer_nif = serializers.CharField(max_length=20, allow_blank=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    lines = LinhaLidaOutSerializer(many=True)


class DocumentoOutSerializer(serializers.Serializer):
    """O `DocumentoOut` da decisão 9 da ADR 0021, campo a campo.

    É a resposta das **cinco** operações que devolvem um documento — criar,
    anexar, fechar, ler um, listar —, e é deliberado: um cliente que faz uma
    escrita recebe o estado completo e não precisa de uma segunda leitura para o
    descobrir (é também o que faz o polling da ADR 0020 poder ser só um `GET`).

    Três campos que merecem nota:

    * `state` é **derivado** e nunca guardado. Ver `models.estado_do_documento`;
    * `expires_at` é `created_at + 15 min`, sempre — também num documento que já
      tem páginas, onde não quer dizer nada. É o que o bloco do QR do desktop usa
      para contar o tempo, e servi-lo nulo depois da primeira página obrigava o
      cliente a guardar o valor anterior;
    * `receipt` é **sempre nulo nesta fatia**. O campo está no contrato desde já
      para o `types.ts` não mudar de forma na fatia 2, que é quando o
      `purchasing_receipt` nasce; hoje não há tabela nenhuma que o possa
      preencher. É a única mentira possível deste payload, e por isso está dita
      aqui.
    """

    id = serializers.UUIDField(source="documento.id")
    source = serializers.ChoiceField(
        source="documento.source", choices=OrigemDoDocumento.choices
    )
    state = serializers.ChoiceField(source="estado", choices=EstadoDoDocumento.choices)
    created_at = serializers.DateTimeField(source="documento.created_at")
    created_by = serializers.CharField(
        source="documento.created_by_name", max_length=150, allow_blank=True
    )
    closed_at = serializers.DateTimeField(source="documento.closed_at", allow_null=True)
    expires_at = serializers.DateTimeField()
    page_count = serializers.IntegerField()
    page_limit = serializers.IntegerField()
    files = FicheiroOutSerializer(source="ficheiros", many=True)
    pages = PaginaOutSerializer(source="paginas", many=True)
    extraction = ExtracaoOutSerializer(source="leitura", allow_null=True)
    receipt = serializers.UUIDField(allow_null=True)


class RecusaDeDocumentoOutSerializer(serializers.Serializer):
    """O corpo de uma recusa: `code` estável para ramificar, `detail` para ler.

    A mesma forma do `ErroOutSerializer` do `accounts`, numa classe própria e não
    reutilizada — o `apps/accounts/serializers.py` não é importável de fora do
    módulo (import-linter: entre módulos só `api.py`), e expor um serializer na
    porta do `accounts` para poupar duas linhas era alargar uma interface pública
    para arrumação.

    Nome diferente (`RecusaDeDocumentoOut`) e não um segundo `ErroOut`: dois
    componentes com o mesmo nome no OpenAPI são um aviso, e o `pnpm gen:api` corre
    com `--fail-on-warn`.

    O `code` é uma string e não um enum fechado, pela razão escrita no `accounts`:
    o conjunto de códigos é **por endpoint** e um enum com a união de todos
    sugeria ao frontend ramos que aquele endpoint nunca devolve. Os códigos de
    cada resposta estão nos docstrings do `views.py`.
    """

    code = serializers.CharField()
    detail = serializers.CharField()
