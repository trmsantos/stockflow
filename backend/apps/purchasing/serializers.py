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

from decimal import Decimal

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
    # Receção de mercadoria
    "CabecalhoInSerializer",
    "LinhaInSerializer",
    "LinhaOutSerializer",
    "RececaoInSerializer",
    "RececaoOutSerializer",
    "ResumoDeRececoesOutSerializer",
    "RevisaoDeLinhaInSerializer",
    "TemperaturaInSerializer",
    "TemperaturaRegistadaOutSerializer",
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


# ============================================================================
# Receção de mercadoria (fatia 2, parte B)
# ============================================================================


class TemperaturaRegistadaOutSerializer(serializers.Serializer):
    """Temperatura registada em receção."""

    conservation = serializers.ChoiceField(choices=["chilled", "frozen"])
    celsius = serializers.DecimalField(max_digits=5, decimal_places=1)
    measured_by = serializers.CharField(max_length=150)
    measured_at = serializers.DateTimeField()


class TemperaturaInSerializer(serializers.Serializer):
    """Entrada de temperatura."""

    conservation = serializers.ChoiceField(choices=["chilled", "frozen"])
    celsius = serializers.DecimalField(max_digits=5, decimal_places=1)


class LocalizacaoReferenceSerializer(serializers.Serializer):
    """Referência a uma localização (para LinhaOut)."""

    id = serializers.UUIDField()
    name = serializers.CharField(max_length=60)


class FornecedorReferenceSerializer(serializers.Serializer):
    """Referência a um fornecedor (para RececaoOut)."""

    name = serializers.CharField(max_length=200)
    nif = serializers.CharField(max_length=20, allow_blank=True)


class EmbalagemReferenceSerializer(serializers.Serializer):
    """Referência a uma embalagem (para LinhaOut)."""

    id = serializers.UUIDField()
    label = serializers.CharField(max_length=60)
    base_quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    base_unit = serializers.CharField(max_length=2)


class PriceHistorySerializer(serializers.Serializer):
    """Histórico de preço (para LinhaOut)."""

    last_price = serializers.DecimalField(max_digits=12, decimal_places=4, allow_null=True)
    unit_label = serializers.CharField(max_length=20, allow_blank=True)
    change_pct = serializers.IntegerField()
    reference = serializers.CharField(max_length=120, allow_blank=True)
    threshold_pct = serializers.IntegerField()


class StockQuantitySerializer(serializers.Serializer):
    """Quantidade em stock após receção."""

    base = serializers.DecimalField(max_digits=12, decimal_places=3)
    base_unit = serializers.CharField(max_length=2)
    display = serializers.DecimalField(max_digits=12, decimal_places=3)
    display_unit = serializers.CharField(max_length=20)


class RececaoInSerializer(serializers.Serializer):
    """Entrada para criar receção."""

    location = serializers.UUIDField()
    document = serializers.UUIDField(required=False, allow_null=True)
    supplier_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    supplier_nif = serializers.CharField(max_length=20, required=False, allow_blank=True)
    doc_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    doc_date = serializers.DateField(required=False, allow_null=True)
    customer_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    customer_nif = serializers.CharField(max_length=20, required=False, allow_blank=True)
    document_total_eur = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    supplier = serializers.UUIDField(required=False, allow_null=True)
    doc_type = serializers.ChoiceField(
        choices=["FT", "FR", "FS", "NC", "ND", "GR"], required=False
    )
    received_at = serializers.DateTimeField(required=False)

    def to_internal_value(self, data):
        """Mapeia os nomes dos campos para os que a função de serviço espera."""
        ret = super().to_internal_value(data)
        # Renomear campos
        if 'location' in ret:
            ret['location_id'] = ret.pop('location')
        if 'document' in ret:
            ret['document_id'] = ret.pop('document')
        if 'supplier' in ret:
            ret['supplier_id'] = ret.pop('supplier')
        return ret


class CabecalhoInSerializer(serializers.Serializer):
    """Entrada para PATCH de cabeçalho (zona da pessoa)."""

    supplier = serializers.UUIDField(required=False, allow_null=True)
    doc_type = serializers.ChoiceField(choices=["FT", "FR", "FS", "NC", "ND", "GR"], required=False)
    received_at = serializers.DateTimeField(required=False)
    location = serializers.UUIDField(required=False)

    def to_internal_value(self, data):
        """Mapeia os nomes dos campos para os que a função de serviço espera."""
        ret = super().to_internal_value(data)
        # Renomear campos
        if 'location' in ret:
            ret['location_id'] = ret.pop('location')
        if 'supplier' in ret:
            ret['supplier_id'] = ret.pop('supplier')
        return ret


class LinhaInSerializer(serializers.Serializer):
    """Entrada para criar linha de receção (à mão)."""

    description = serializers.CharField(max_length=500)
    invoice_unit = serializers.CharField(max_length=20)
    quantity_invoiced = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=4, required=False, allow_null=True)
    discount_pct = serializers.DecimalField(max_digits=6, decimal_places=3, required=False, allow_null=True)
    vat_rate = serializers.DecimalField(max_digits=6, decimal_places=3, required=False, allow_null=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    supplier_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    ean = serializers.CharField(max_length=14, required=False, allow_blank=True)
    variable_weight = serializers.BooleanField(required=False, default=False)
    kind = serializers.ChoiceField(
        choices=["goods", "deposit", "charge", "document_ref"], required=False, default="goods"
    )
    # Campos de revisão opcionais (zona da pessoa)
    product = serializers.UUIDField(required=False, allow_null=True)
    packaging = serializers.UUIDField(required=False, allow_null=True)
    base_per_invoice_unit = serializers.DecimalField(
        max_digits=12, decimal_places=3, required=False, allow_null=True
    )
    quantity_received = serializers.DecimalField(
        max_digits=12, decimal_places=3, required=False
    )
    location = serializers.UUIDField(required=False)
    lot_code = serializers.CharField(max_length=40, required=False, allow_blank=True)
    expires_at = serializers.DateField(required=False, allow_null=True)


class RevisaoDeLinhaInSerializer(serializers.Serializer):
    """Entrada para rever linha."""

    product = serializers.UUIDField(required=False, allow_null=True)
    packaging = serializers.UUIDField(required=False, allow_null=True)
    base_per_invoice_unit = serializers.DecimalField(
        max_digits=12, decimal_places=3, required=False, allow_null=True
    )
    quantity_received = serializers.DecimalField(
        max_digits=12, decimal_places=3, required=False
    )
    location = serializers.UUIDField(required=False)
    kind = serializers.ChoiceField(
        choices=["goods", "deposit", "charge", "document_ref"], required=False
    )
    lot_code = serializers.CharField(max_length=40, required=False, allow_blank=True)
    expires_at = serializers.DateField(required=False, allow_null=True)
    skip = serializers.BooleanField(required=False, default=False)

    def validate(self, data):
        """Validações entre campos."""
        # If kind is "goods" and product is provided, check track_lots requirement
        kind = data.get("kind", "goods")
        lot_code = data.get("lot_code", "").strip()
        expires_at = data.get("expires_at")
        product_id = data.get("product")

        if kind == "goods" and product_id:
            from apps.catalog.api import produto_por_id
            request = self.context.get('request')
            if request and hasattr(request, 'tenant'):
                tenant_id = request.tenant.id
                produto = produto_por_id(tenant_id=tenant_id, product_id=product_id)
                # Lot is mandatory if track_lots=True
                if produto and produto.track_lots and not lot_code:
                    raise serializers.ValidationError({
                        "lot_code": [_("Lot code is required for items that track lots.")]
                    })

        # If lot_code is provided, expires_at is mandatory
        if lot_code and not expires_at:
            raise serializers.ValidationError({
                "expires_at": [_("Expiry date is required when lot code is provided.")]
            })

        return data


class LinhaOutSerializer(serializers.Serializer):
    """Saída de linha de receção."""

    id = serializers.UUIDField()
    position = serializers.IntegerField()
    description = serializers.CharField(max_length=500)
    product = serializers.UUIDField(allow_null=True)
    product_name = serializers.CharField(max_length=80, allow_null=True)
    kind = serializers.ChoiceField(choices=["goods", "deposit", "charge", "document_ref"])
    status = serializers.ChoiceField(choices=["needs_review", "confirmed", "skipped"])
    conservation = serializers.ChoiceField(choices=["ambient", "chilled", "frozen"])
    location = LocalizacaoReferenceSerializer()
    invoice_unit = serializers.CharField(max_length=20)
    quantity_invoiced = serializers.DecimalField(max_digits=12, decimal_places=3, allow_null=True)
    quantity_received = serializers.DecimalField(max_digits=12, decimal_places=3)
    packaging = EmbalagemReferenceSerializer(allow_null=True)
    base_per_invoice_unit = serializers.DecimalField(
        max_digits=12, decimal_places=3, allow_null=True
    )
    stock_quantity = StockQuantitySerializer(allow_null=True)
    variable_weight = serializers.BooleanField()
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=4, allow_null=True)
    discount_pct = serializers.DecimalField(max_digits=6, decimal_places=3, allow_null=True)
    vat_rate = serializers.DecimalField(max_digits=6, decimal_places=3, allow_null=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    supplier_code = serializers.CharField(max_length=50, allow_blank=True)
    ean = serializers.CharField(max_length=14, allow_blank=True)
    price_history = PriceHistorySerializer(allow_null=True)
    requires_lot = serializers.BooleanField()
    lot_code = serializers.CharField(max_length=40, allow_blank=True)
    expires_at = serializers.DateField(allow_null=True)
    expiry_kind = serializers.CharField(max_length=20, allow_null=True)
    reviewed_by = serializers.CharField(max_length=150, allow_null=True)
    reviewed_at = serializers.DateTimeField(allow_null=True)
    movement = serializers.UUIDField(allow_null=True)


class VatBreakdownSerializer(serializers.Serializer):
    """Breakdown de IVA."""

    rate = serializers.DecimalField(max_digits=6, decimal_places=3)
    base = serializers.DecimalField(max_digits=12, decimal_places=2)
    vat = serializers.DecimalField(max_digits=12, decimal_places=2)


class RececaoOutSerializer(serializers.Serializer):
    """Saída de receção."""

    id = serializers.UUIDField(source="receipt.id")
    document = serializers.UUIDField(source="receipt.document_id", allow_null=True)
    supplier = serializers.SerializerMethodField()
    supplier_id = serializers.UUIDField(source="receipt.supplier_id", allow_null=True)
    doc_type = serializers.ChoiceField(
        source="receipt.doc_type",
        choices=["FT", "FR", "FS", "NC", "ND", "GR"]
    )
    doc_number = serializers.CharField(source="receipt.doc_number", max_length=100, allow_blank=True)
    doc_date = serializers.DateField(source="receipt.doc_date", allow_null=True)
    received_at = serializers.DateTimeField(source="receipt.received_at")
    confirmed_at = serializers.DateTimeField(source="receipt.confirmed_at", allow_null=True)
    confirmed_by = serializers.CharField(source="receipt.confirmed_by_name", max_length=150, allow_null=True)
    status = serializers.SerializerMethodField()
    lines_to_review = serializers.SerializerMethodField()
    line_count = serializers.SerializerMethodField()
    customer_name = serializers.CharField(source="receipt.customer_name", max_length=200, allow_blank=True)
    customer_nif = serializers.CharField(source="receipt.customer_nif", max_length=20, allow_blank=True)
    company_name = serializers.SerializerMethodField()
    company_nif = serializers.SerializerMethodField()
    awaiting_invoice = serializers.SerializerMethodField()
    document_total = serializers.DecimalField(source="receipt.document_total_eur", max_digits=12, decimal_places=2, allow_null=True)
    lines_total = serializers.SerializerMethodField()
    vat_breakdown = serializers.SerializerMethodField()
    temperatures = serializers.SerializerMethodField()
    cold_chain = serializers.SerializerMethodField()
    location = serializers.SerializerMethodField()
    locations = serializers.SerializerMethodField()
    reference = serializers.CharField(source="receipt.reference", max_length=120, allow_blank=True)

    def get_supplier(self, obj):
        """Extrai supplier do receipt."""
        return {
            "name": obj["receipt"].supplier_name,
            "nif": obj["receipt"].supplier_nif,
        }

    def get_status(self, obj):
        """Determina status da receção."""
        return "confirmed" if obj["receipt"].confirmed_at else "needs_review"

    def get_lines_to_review(self, obj):
        """Conta linhas que precisam de revisão."""
        return sum(1 for l in obj["linhas"] if l["linha"].status == "needs_review")

    def get_line_count(self, obj):
        """Total de linhas."""
        return len(obj["linhas"])

    def get_company_name(self, obj):
        """Nome da empresa (tenant)."""
        return obj["receipt"].tenant.name if obj["receipt"].tenant else ""

    def get_company_nif(self, obj):
        """NIF da empresa (tenant)."""
        return ""

    def get_awaiting_invoice(self, obj):
        """Retorna True se está a aguardar fatura."""
        return obj["receipt"].document_id is not None and obj["receipt"].confirmed_at is None

    def get_lines_total(self, obj):
        """Soma dos totais das linhas."""
        total = Decimal(0)
        for linha_data in obj["linhas"]:
            if linha_data["linha"].line_total:
                total += linha_data["linha"].line_total
        return total if total else None

    def get_vat_breakdown(self, obj):
        """Breakdown de IVA."""
        # Agrupar linhas por taxa de IVA
        vat_map = {}
        for linha_data in obj["linhas"]:
            linha = linha_data["linha"]
            if linha.status != "skipped" and linha.vat_rate:
                rate = str(linha.vat_rate)
                if rate not in vat_map:
                    vat_map[rate] = {"base": Decimal(0), "vat": Decimal(0)}
                if linha.line_total and linha.vat_rate:
                    vat_amount = linha.line_total * (linha.vat_rate / Decimal(100))
                    vat_map[rate]["vat"] += vat_amount
                    vat_map[rate]["base"] += linha.line_total - vat_amount

        return [
            {
                "rate": Decimal(rate),
                "base": value["base"],
                "vat": value["vat"],
            }
            for rate, value in sorted(vat_map.items())
        ]

    def get_temperatures(self, obj):
        """Temperaturas registadas."""
        temps = []
        receipt = obj["receipt"]
        if receipt.chilled_temperature_c is not None:
            temps.append({
                "conservation": "chilled",
                "celsius": receipt.chilled_temperature_c,
                "measured_by": receipt.chilled_measured_by_name or "",
                "measured_at": receipt.chilled_measured_at,
            })
        if receipt.frozen_temperature_c is not None:
            temps.append({
                "conservation": "frozen",
                "celsius": receipt.frozen_temperature_c,
                "measured_by": receipt.frozen_measured_by_name or "",
                "measured_at": receipt.frozen_measured_at,
            })
        return temps

    def get_cold_chain(self, obj):
        """Retorna True se há registos de temperatura."""
        receipt = obj["receipt"]
        return (
            receipt.chilled_temperature_c is not None or
            receipt.frozen_temperature_c is not None
        )

    def get_location(self, obj):
        """Localização principal da receção."""
        locais = obj["locais"]
        receipt = obj["receipt"]
        local = locais.get(receipt.location_id)
        if local:
            return {
                "id": local.id,
                "name": local.name,
            }
        return None

    def get_locations(self, obj):
        """Todas as localizações usadas."""
        locais = obj["locais"]
        return [
            {
                "id": local.id,
                "name": local.name,
            }
            for local in locais.values()
        ]


class ResumoDeRececoesOutSerializer(serializers.Serializer):
    """Resumo de receções."""

    needs_review_count = serializers.IntegerField()
    needs_review_lines = serializers.IntegerField()
    confirmed_today_count = serializers.IntegerField()
    business_day_starts_at = serializers.TimeField()
    confirmed_since = serializers.DateTimeField()
