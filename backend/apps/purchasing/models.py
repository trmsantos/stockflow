"""As três tabelas do documento do fornecedor (ADR 0021, fatia 1).

| Tabela | O que é |
|---|---|
| `purchasing_invoicedocument` | o **documento físico**: o slot, o autor, o fecho, o descarte |
| `purchasing_documentfile` | cada **ficheiro** que lhe entrou: bytes, tipo real, sha256 |
| `purchasing_documentpage` | cada **página**: a imagem normalizada, e o QR quando houver |

Três tabelas e não uma, pela razão medível da ADR 0021: **um PDF de dez páginas é
um ficheiro e dez páginas; duas fotografias são dois ficheiros e duas páginas**, e
a contagem não é a mesma. O `sha256` único por documento é o que faz uma
retentativa em rede má não criar uma página duplicada — e uma página duplicada é
uma linha duplicada é uma entrada de stock duplicada.

O que **não** está aqui, e é decisão e não omissão:

* **nenhuma coluna de cabeçalho** (fornecedor, número, total). O documento é o
  papel; o que o papel *diz* é a receção, que é da fatia 2. Uma fotografia de um
  gato tem páginas e nunca tem receção (ADR 0020, decisão 8);
* **nenhuma coluna de captura** (`capture_token_hash`, `capture_expires_at`). A
  adenda 2 da ADR 0020 revogou o token ao portador: a ponte é a sessão do
  telemóvel, e o slot é `created_at` + 15 minutos + zero páginas, **derivado**;
* **nenhuma coluna de estado.** `EstadoDoDocumento` é lido dos timestamps e da
  última extração, como o `EstadoDoConvite` da ADR 0010 e pela mesma razão: um
  timeout não escreve linha nenhuma, logo um estado em coluna estaria errado
  quinze minutos depois.

Nenhum destes modelos é registado no admin (ADR 0007).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.shared.models import TenantModel

__all__ = [
    "DocumentFile",
    "DocumentPage",
    "EstadoDaLeitura",
    "EstadoDoDocumento",
    "InvoiceDocument",
    "OrigemDoDocumento",
    "Receipt",
    "ReceiptLine",
    "estado_do_documento",
]

#: Quantas páginas cabem num documento. **Constante de módulo e não coluna**: é a
#: resposta por omissão à primeira das três perguntas que a ADR 0021 deixou ao
#: dono ("qual é o documento com mais páginas que lhe entra por mês — e dez
#: chega?"), e sobe com uma linha. Uma coluna fazia parecer que o teto é
#: configurável por estabelecimento, que é uma afirmação de produto que ninguém
#: fez. É simétrico ao teto de páginas de PDF da decisão 4 da ADR 0020.
PAGINAS_POR_DOCUMENTO = 10

#: Quanto tempo um slot vazio espera pela primeira página. **Um relógio só** (ADR
#: 0020, decisão 1c): o mesmo valor decide `aguarda_captura` contra `expirado` e
#: o que a tarefa de limpeza varre. Dois relógios divergem, e um slot `expirado`
#: no ecrã que ainda aceitasse páginas seria a pior divergência possível.
JANELA_DO_SLOT = timedelta(minutes=15)

#: Quanto tempo uma extração pode estar em curso antes de se ler como `erro`. O
#: `a_extrair` precisa de um relógio porque uma tarefa morta deixaria o estado
#: preso para sempre (ADR 0021, decisão 9).
JANELA_DA_EXTRACAO = timedelta(minutes=10)


class OrigemDoDocumento(models.TextChoices):
    """Por onde o documento entrou. É coluna, ao contrário do estado.

    **Derivada no serviço e não declarada pelo cliente** (ver
    `services.criar_documento`): um pedido de criação que traz ficheiro é
    `upload`; um que vem vazio é o slot que o QR nomeia, logo `capture`. É o que
    decide também quem fecha o documento — um ficheiro fecha-se a si mesmo, uma
    captura é fechada por uma pessoa (ADR 0021, decisão 9).
    """

    UPLOAD = "upload", "ficheiro enviado"
    CAPTURE = "capture", "fotografado no telemóvel"


class EstadoDoDocumento(models.TextChoices):
    """Em que ponto da sua vida está um documento. **Derivado, nunca guardado.**

    Oito valores, que são os seis da decisão 9 da ADR 0021 mais o `erro` que a
    mesma decisão nomeia na frase do relógio e o `expirado` da decisão 2 da ADR
    0020. É um `TextChoices` para o `ChoiceField` do serializer o emitir como
    enum fechado no OpenAPI: a união chega ao `types.ts` commitado e o `switch`
    do frontend deixa de poder esquecer um ramo.

    A precedência está em `estado_do_documento`, que é onde a leitura vive.
    """

    AGUARDA_CAPTURA = "aguarda_captura", "slot aberto, à espera da primeira página"
    EXPIRADO = "expirado", "o slot expirou sem página nenhuma"
    A_NORMALIZAR = "a_normalizar", "há páginas e a imagem ainda não está pronta"
    A_EXTRAIR = "a_extrair", "o modelo está a ler o documento"
    LIDO = "lido", "o modelo leu e o resultado está disponível"
    ILEGIVEL = "ilegivel", "o modelo respondeu algo que não se consegue validar"
    ERRO = "erro", "a extração falhou ou nunca acabou"
    DESCARTADO = "descartado", "descartado por uma pessoa"


class EstadoDaLeitura(models.TextChoices):
    """O estado de uma chamada ao modelo, **como o `purchasing` o vê**.

    Não é coluna de nenhuma tabela deste módulo: é o vocabulário do porto que o
    `api.py` reexporta e que o `agents` preenche (ver `apps/purchasing/api.py`).
    Vive aqui, ao lado do `EstadoDoDocumento`, porque é a outra metade da mesma
    derivação — e aqui em vez de no `api.py` para que o `models.py` não tenha de
    importar o `api.py`, que importa os selectors, que importam este ficheiro.

    Os quatro valores são os mesmos do `status` do `agents_extraction`, e a
    igualdade das duas listas é um teste (`tests/test_extracao.py`): são duas
    listas fechadas em módulos diferentes, e é a divergência entre elas que
    ninguém veria.
    """

    PENDENTE = "pendente", "a chamada começou e não acabou"
    LIDO = "lido", "o modelo respondeu e a resposta valida"
    ILEGIVEL = "ilegivel", "o modelo respondeu e a resposta não valida"
    ERRO = "erro", "a chamada falhou"


def estado_do_documento(
    *,
    discarded_at: datetime | None,
    created_at: datetime,
    page_count: int,
    estado_da_leitura: str | None = None,
    leitura_desde: datetime | None = None,
    agora: datetime | None = None,
) -> str:
    """O `EstadoDoDocumento` de um documento, lido do relógio e de mais nada.

    Função de módulo e não `@property` do modelo por uma razão que não é estilo:
    metade da entrada vem de **fora** deste módulo — o estado da última chamada
    ao modelo vive no `agents_extraction`, que o `purchasing` não pode ler
    (import-linter). Uma propriedade teria de ir buscá-la, e não pode; uma função
    pura recebe-a de quem a tem e fica testável sem base de dados nenhuma.

    A ordem dos ramos **é** a precedência, e cada uma tem um porquê:

    1. `descartado` ganha a tudo. Uma pessoa disse que este documento não
       interessa, e isso não se desfaz por o relógio andar;
    2. **zero páginas é o slot**, e aí o único facto é o relógio: `aguarda_captura`
       dentro dos 15 minutos, `expirado` depois (ADR 0020, decisão 2). Um
       documento vazio nunca aparece na lista do Receber — é o `selectors.py` que
       o filtra;
    3. com páginas e **sem chamada nenhuma ao modelo**, `a_normalizar`: é o que
       está a acontecer, quer a imagem ainda não esteja pronta, quer o documento
       ainda esteja aberto à espera da segunda folha;
    4. com uma chamada em curso, `a_extrair` **enquanto o relógio deixar** e
       `erro` depois. Sem este relógio uma tarefa morta deixava o estado preso
       para sempre (ADR 0021, decisão 9).
    """
    agora = agora or timezone.now()
    if discarded_at is not None:
        return EstadoDoDocumento.DESCARTADO
    if page_count == 0:
        if agora < created_at + JANELA_DO_SLOT:
            return EstadoDoDocumento.AGUARDA_CAPTURA
        return EstadoDoDocumento.EXPIRADO
    if estado_da_leitura is None:
        return EstadoDoDocumento.A_NORMALIZAR
    if estado_da_leitura == EstadoDaLeitura.LIDO:
        return EstadoDoDocumento.LIDO
    if estado_da_leitura == EstadoDaLeitura.ILEGIVEL:
        return EstadoDoDocumento.ILEGIVEL
    if estado_da_leitura == EstadoDaLeitura.ERRO:
        return EstadoDoDocumento.ERRO
    desde = leitura_desde or created_at
    if agora < desde + JANELA_DA_EXTRACAO:
        return EstadoDoDocumento.A_EXTRAIR
    return EstadoDoDocumento.ERRO


class InvoiceDocument(TenantModel):
    """Um documento de fornecedor que entrou — por ficheiro ou por fotografia.

    Herda de `TenantModel`: chave UUID, `tenant_id` que a política compara, os
    dois timestamps e o índice `(tenant_id, -created_at)` de todas as listagens.
    Herdar daqui é também a declaração de que a migração que cria a tabela traz o
    bloco de RLS (CLAUDE.md).

    ## Existe antes do ficheiro, e é isso que o torna um slot

    A ponte para o telemóvel não acrescenta tabela nenhuma (ADR 0020, decisão 2):
    o desktop cria **este** registo sem ficheiro, o QR nomeia-o pelos dois uuid
    em search params, e o telemóvel anexa-lhe páginas com a sua própria sessão.
    Daí não haver nenhuma coluna obrigatória que descreva conteúdo.

    ## `closed_at` e `discarded_at`, e nada entre os dois

    `closed_at` é "não vêm mais páginas", e é o que dispara a extração.
    `discarded_at` é "isto não interessa" — descarte **suave**, porque o
    apagamento a sério do original é a segunda pergunta que o dono ainda não
    respondeu (quanto tempo se guarda a fatura, e se o contabilista precisa do
    ficheiro). Os bytes só desaparecem quando não há páginas, e é o `services.py`
    que o decide.

    ## `created_by` e `created_by_name` ao lado

    O FK é `SET_NULL`: apagar a conta de quem enviou não pode apagar o documento
    que ela enviou. O nome fica copiado porque é o nome **naquele**
    estabelecimento (vive no `Membership`, que é uma tabela com política) e porque
    uma listagem que mostrasse o autor por travessia pagava um join por linha
    para um texto que nunca muda depois de escrito.
    """

    source = models.CharField(
        max_length=20,
        choices=OrigemDoDocumento.choices,
        editable=False,
        verbose_name="origem",
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        editable=False,
        verbose_name="fechado em",
    )
    discarded_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        editable=False,
        verbose_name="descartado em",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
        verbose_name="enviado por",
    )
    created_by_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        editable=False,
        verbose_name="nome de quem enviou",
    )

    class Meta(TenantModel.Meta):
        verbose_name = "documento de fornecedor"
        verbose_name_plural = "documentos de fornecedor"

    def __str__(self) -> str:
        return f"{self.source} {self.pk}"


class DocumentFile(TenantModel):
    """Um ficheiro que entrou neste documento. Os bytes vivem fora da base.

    ## O nome no disco é gerado; o do cliente é um rótulo

    `path` é `<uuid>.<extensão>` debaixo do `MEDIA_ROOT` e nunca contém nada que
    tenha vindo do pedido (SECURITY.md §4). `original_filename` guarda-se para a
    pessoa reconhecer o que enviou e **nunca** entra num caminho — é o que o
    `services.py` garante por construção, porque o caminho é composto a partir do
    uuid e da extensão derivada do tipo real.

    ## `content_type` é o que os bytes dizem, não o que o cliente declara

    O `Content-Type` do pedido é **ignorado**, não validado (ADR 0020, decisão 4):
    um cliente que minta no header com os bytes certos é aceite, e um que acerte
    no header com os bytes errados é recusado. Quem decide é
    `apps/purchasing/ficheiros.py`, por bytes mágicos e sobre uma lista fechada.

    ## `sha256` com unicidade por documento

    É a rede contra a retentativa: uma rede má que repita o POST da mesma
    fotografia não cria um segundo ficheiro nem uma segunda página. Por
    **documento** e não global de propósito — a mesma fatura pode legitimamente
    chegar a dois estabelecimentos, e o mesmo ficheiro pode ser enviado a dois
    documentos diferentes pela mesma pessoa a corrigir-se.

    `pages_detected` é quantas páginas estes bytes têm. Para uma imagem é 1; para
    um PDF é o que o contador em Python puro do `ficheiros.py` consegue dizer, com
    os limites desse contador escritos lá.
    """

    document = models.ForeignKey(
        "purchasing.InvoiceDocument",
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="documento",
    )
    position = models.PositiveSmallIntegerField(editable=False, verbose_name="ordem")
    path = models.CharField(
        max_length=255,
        editable=False,
        verbose_name="caminho no armazenamento",
    )
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        default="",
        editable=False,
        verbose_name="nome que o cliente deu",
    )
    content_type = models.CharField(
        max_length=100,
        editable=False,
        verbose_name="tipo real dos bytes",
    )
    byte_size = models.PositiveIntegerField(editable=False, verbose_name="tamanho em bytes")
    sha256 = models.CharField(max_length=64, editable=False, verbose_name="SHA-256 dos bytes")
    pages_detected = models.PositiveSmallIntegerField(
        editable=False,
        verbose_name="páginas detetadas",
    )

    class Meta(TenantModel.Meta):
        verbose_name = "ficheiro de documento"
        verbose_name_plural = "ficheiros de documento"
        constraints = [
            # A rede contra a retentativa. `UniqueConstraint` e não `unique=True`
            # no campo pela razão medida no `Invitation.token_hash`: num campo de
            # texto, o `unique=True` faz o Django criar também um índice
            # `varchar_pattern_ops` para servir `LIKE`, e ninguém procura um
            # digest por prefixo.
            models.UniqueConstraint(
                fields=["document", "sha256"],
                name="documentfile_document_sha256_uniq",
            ),
            models.UniqueConstraint(
                fields=["document", "position"],
                name="documentfile_document_position_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.content_type} #{self.position}"


class DocumentPage(TenantModel):
    """Uma página do documento: o que o ecrã de revisão mostra e o modelo vê.

    ## Nasce **antes** da imagem

    `image_path`, `width`, `height` e `normalized_at` são todos nuláveis, e é
    isso que diz quando a linha nasce: no upload, a partir do
    `pages_detected` do ficheiro. A rasterização preenche-os depois, no worker —
    nenhum decoder nativo corre no processo que serve pedidos (ADR 0020, decisão
    4). Enquanto `normalized_at` for nulo não há imagem para servir, e o endpoint
    da imagem responde 404.

    ## `document` **e** `file`, as duas

    O `file` é a proveniência (de que bytes saiu esta página) e o `document` é o
    sítio onde ela se ordena. Sem o `document`, a ordem das páginas de um
    documento com duas fotografias era uma query sobre duas tabelas; sem o
    `file`, a retentativa não tinha como não duplicar a página.

    ## `qr_payload`, e quem o escreve desde 2026-10-19

    Desde 1/1/2023 toda a fatura portuguesa imprime um QR que traz, legível por
    máquina e **sem erro de OCR**, os dois NIF, o tipo e o estado do documento, a
    data, o ATCUD, o espaço fiscal e as bases e o IVA por taxa. Logo **o QR é a
    verdade do cabeçalho e o LLM só serve para as linhas** (ADR 0021, adenda).

    A coluna entrou antes da leitura, porque era grátis e porque a biblioteca que
    descodifica um QR era uma dependência por decidir. **O dono decidiu a
    2026-10-19: `zxing-cpp`** — instala-se como qualquer pacote Python, não
    acrescenta nada à imagem Docker, e lê QR fotografados de lado. Desde então há
    exactamente **um** sítio que escreve aqui: a `services.registar_normalizacao`,
    com o texto que a `rasterizacao.rasterizar` leu da mesma imagem que
    normalizou, na mesma transação que a largura e a altura. Não há endpoint nem
    revisão que mexa nisto: o que está nesta coluna foi lido de uma imagem.

    Vazio continua a ser um caso normal e **não um erro**: uma página sem QR, um
    QR dobrado, uma fotografia tremida. Aí o cabeçalho vem da extração, como
    vinha antes de a coluna ter quem a escrevesse.

    **A coluna é texto vazio e não NULL, contra o que a ADR escreve**, e a razão
    é o lint: o `DJ001` do ruff recusa `null=True` num campo de texto e o
    `CLAUDE.md` não deixa suprimir uma regra. Não se perde informação: `""`
    significa "não houve leitura", e um QR que descodifique para a string vazia
    não existe.
    """

    document = models.ForeignKey(
        "purchasing.InvoiceDocument",
        on_delete=models.CASCADE,
        related_name="pages",
        verbose_name="documento",
    )
    file = models.ForeignKey(
        "purchasing.DocumentFile",
        on_delete=models.CASCADE,
        related_name="pages",
        verbose_name="ficheiro de origem",
    )
    file_page_number = models.PositiveSmallIntegerField(
        editable=False,
        verbose_name="página dentro do ficheiro",
    )
    position = models.PositiveSmallIntegerField(editable=False, verbose_name="ordem no documento")
    image_path = models.CharField(
        max_length=255,
        blank=True,
        default="",
        editable=False,
        verbose_name="caminho da imagem normalizada",
    )
    width = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        editable=False,
        verbose_name="largura em píxeis",
    )
    height = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        editable=False,
        verbose_name="altura em píxeis",
    )
    normalized_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        editable=False,
        verbose_name="normalizada em",
    )
    qr_payload = models.TextField(
        blank=True,
        default="",
        editable=False,
        verbose_name="conteúdo do QR da fatura",
    )

    class Meta(TenantModel.Meta):
        verbose_name = "página de documento"
        verbose_name_plural = "páginas de documento"
        constraints = [
            models.UniqueConstraint(
                fields=["document", "position"],
                name="documentpage_document_position_uniq",
            ),
            models.UniqueConstraint(
                fields=["file", "file_page_number"],
                name="documentpage_file_page_uniq",
            ),
        ]

    @property
    def image_url(self) -> str:
        """O caminho do endpoint que serve os bytes desta página.

        É a forma do `get_absolute_url` do Django: uma propriedade que resolve
        por `reverse` e nunca um f-string, porque o path vive no `urls.py` e uma
        segunda cópia dele divergia no dia em que alguém o mudasse.

        Vive no modelo e não num `SerializerMethodField` por uma razão medida: o
        `COMPONENT_NO_READ_ONLY_REQUIRED` do drf-spectacular marca um campo de
        método como **opcional** no componente de resposta, e o `types.ts`
        passava a prometer `image_url?: string` num campo que o servidor manda
        sempre — um tipo a mentir na direcção que obriga o cliente a tratar um
        caso que não existe. Com uma propriedade, o serializer declara um
        `CharField` normal.

        Caminho relativo e não URL absoluto, pela razão da ADR 0010: o backend
        não conhece a origem da SPA.
        """
        return reverse(
            "api:documento-imagem",
            kwargs={"pk": str(self.document_id), "posicao": self.position},
        )

    @property
    def normalized(self) -> bool:
        """Já há imagem para esta página?

        Propriedade e não coluna: é a leitura de `normalized_at`, e uma segunda
        coluna booleana ao lado de um timestamp que a determina são duas fontes
        de verdade. É o que o `PaginaOut` serve, e é também o que diz ao cliente
        se vale a pena pedir o `image_url`.
        """
        return self.normalized_at is not None

    def __str__(self) -> str:
        return f"página {self.position}"


class Receipt(TenantModel):
    """Uma receção de mercadoria — o cabeçalho e as linhas.

    Liga o documento de fatura (fatia 1) ao catálogo (parte A). Tem duas zonas:
    - **zona do documento**: o que o papel impresso diz (lido uma vez, pode ser corrigido na criação).
    - **zona da pessoa**: o que o utilizador revê e confirma.

    A receção nasce com `status = needs_review` e pode passar a `confirmed` quando
    o utilizador confirma (fatia 3 escreve `movement_id`). As linhas são `needs_review`,
    `confirmed` ou `skipped` — trata-se de uma linha revista pelo utilizador.

    Herda de `TenantModel` — política RLS por `tenant_id`.
    """

    # Ligação ao documento
    document = models.ForeignKey(
        "purchasing.InvoiceDocument",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="+",
        verbose_name="documento de fatura",
    )

    # Zona do documento — lida uma vez, correível na criação
    supplier_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="nome do fornecedor como impresso",
    )
    supplier_nif = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="NIF do fornecedor como impresso",
    )
    doc_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="número de documento como impresso",
    )
    doc_number_normalized = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="número de documento normalizado",
    )
    doc_date = models.DateField(
        null=True,
        blank=True,
        default=None,
        verbose_name="data do documento",
    )
    atcud = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="ATCUD da fatura",
    )
    fiscal_space = models.CharField(
        max_length=5,
        blank=True,
        default="",
        verbose_name="espaço fiscal",
    )
    customer_name = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="nome do cliente",
    )
    customer_nif = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="NIF do cliente",
    )
    document_total_eur = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        verbose_name="total do documento em EUR",
    )

    # Zona da pessoa — revista e confirmada
    supplier = models.ForeignKey(
        "catalog.Supplier",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        default=None,
        related_name="+",
        verbose_name="fornecedor do catálogo",
    )
    doc_type = models.CharField(
        max_length=2,
        choices=[
            ("FT", "Fatura"),
            ("FR", "Fatura-Recibo"),
            ("FS", "Fatura Simplificada"),
            ("NC", "Nota de Crédito"),
            ("ND", "Nota de Débito"),
            ("GR", "Guia de Remessa"),
        ],
        verbose_name="tipo de documento",
    )
    received_at = models.DateTimeField(verbose_name="recebido em")
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.RESTRICT,
        related_name="+",
        verbose_name="localização de destino",
    )
    settled_by = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="+",
        verbose_name="liquidado por",
    )
    reference = models.CharField(
        max_length=120,
        blank=True,
        default="",
        verbose_name="referência para o ledger",
    )

    # Temperatura — pares de colunas
    chilled_temperature_c = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        default=None,
        verbose_name="temperatura refrigerado (°C)",
    )
    chilled_measured_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        verbose_name="temperatura refrigerado medida em",
    )
    chilled_measured_by_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="temperatura refrigerado medida por",
    )
    frozen_temperature_c = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        default=None,
        verbose_name="temperatura congelado (°C)",
    )
    frozen_measured_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        verbose_name="temperatura congelado medida em",
    )
    frozen_measured_by_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="temperatura congelado medida por",
    )

    # Confirmação
    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        verbose_name="confirmada em",
    )
    confirmed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="+",
        verbose_name="confirmada por",
    )
    confirmed_by_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="confirmada por (nome)",
    )

    # Quem criou
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="+",
        verbose_name="criada por",
    )
    created_by_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="criada por (nome)",
    )

    class Meta(TenantModel.Meta):
        verbose_name = "receção de mercadoria"
        verbose_name_plural = "receções de mercadoria"
        constraints = [
            # Unicidade parcial: documento-tenant
            models.UniqueConstraint(
                fields=["tenant", "document"],
                name="receipt_tenant_document_uniq",
                condition=models.Q(document__isnull=False),
            ),
            # Chave de duplicado: (tenant, supplier_nif, doc_type, doc_number_normalized)
            models.UniqueConstraint(
                fields=["tenant", "supplier_nif", "doc_type", "doc_number_normalized"],
                name="receipt_tenant_supplier_nif_doc_type_number_uniq",
                condition=models.Q(doc_number_normalized__gt=""),
            ),
            # Chave de ATCUD: (tenant, atcud)
            models.UniqueConstraint(
                fields=["tenant", "atcud"],
                name="receipt_tenant_atcud_uniq",
                condition=models.Q(atcud__gt=""),
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "confirmed_at"]),
            models.Index(fields=["tenant", "-received_at"]),
        ]

    def __str__(self) -> str:
        return f"Receção {self.reference or self.doc_number or self.pk}"


class ReceiptLine(TenantModel):
    """Uma linha de receção — um item do documento.

    Tem duas zonas análogas ao `Receipt`:
    - **zona do documento**: o que o papel impresso diz.
    - **zona da pessoa**: o que o utilizador revê, confirma e eventualmente entra no stock.

    O status é `needs_review` (inicial), `confirmed` (revista e aprovada) ou
    `skipped` (revista e rejeitada — e.g., "faltou esta linha").

    Herda de `TenantModel` — política RLS por `tenant_id`.
    """

    receipt = models.ForeignKey(
        "purchasing.Receipt",
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="receção",
    )
    position = models.PositiveSmallIntegerField(verbose_name="posição")

    # Zona do documento — lida uma vez
    description = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="descrição como impresso",
    )
    invoice_unit = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="unidade da fatura",
    )
    quantity_invoiced = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        default=None,
        verbose_name="quantidade na fatura",
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        default=None,
        verbose_name="preço unitário",
    )
    discount_pct = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
        default=None,
        verbose_name="percentagem de desconto",
    )
    vat_rate = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        null=True,
        blank=True,
        default=None,
        verbose_name="taxa de IVA",
    )
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        verbose_name="total da linha",
    )
    supplier_code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name="código do fornecedor",
    )
    ean = models.CharField(
        max_length=14,
        blank=True,
        default="",
        verbose_name="EAN/código de barras",
    )
    variable_weight = models.BooleanField(
        default=False,
        verbose_name="peso variável",
    )
    extraction_confidence = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
        default=None,
        verbose_name="confiança de extração",
    )

    # Zona da pessoa — revista e confirmada
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        default=None,
        related_name="+",
        verbose_name="artigo do catálogo",
    )
    packaging = models.ForeignKey(
        "catalog.ProductPackaging",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        default=None,
        related_name="+",
        verbose_name="embalagem",
    )
    base_per_invoice_unit = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        default=None,
        verbose_name="unidades base por unidade de fatura",
    )
    quantity_received = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name="quantidade recebida",
    )
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.RESTRICT,
        related_name="+",
        verbose_name="localização",
    )
    kind = models.CharField(
        max_length=20,
        choices=[
            ("goods", "Mercadoria"),
            ("deposit", "Vasilhame"),
            ("charge", "Encargo"),
            ("document_ref", "Referência de Documento"),
        ],
        verbose_name="tipo de linha",
    )
    lot_code = models.CharField(
        max_length=40,
        blank=True,
        default="",
        verbose_name="lote",
    )
    expires_at = models.DateField(
        null=True,
        blank=True,
        default=None,
        verbose_name="data de expiração",
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("needs_review", "Precisa de Revisão"),
            ("confirmed", "Confirmada"),
            ("skipped", "Saltada"),
        ],
        default="needs_review",
        verbose_name="estado",
    )
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name="+",
        verbose_name="revista por",
    )
    reviewed_by_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name="revista por (nome)",
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        default=None,
        verbose_name="revista em",
    )
    movement_id = models.UUIDField(
        null=True,
        blank=True,
        default=None,
        verbose_name="movimento de stock",
    )

    class Meta(TenantModel.Meta):
        verbose_name = "linha de receção"
        verbose_name_plural = "linhas de receção"
        constraints = [
            # Posição única por receção
            models.UniqueConstraint(
                fields=["receipt", "position"],
                name="receiptline_receipt_position_uniq",
            ),
            # Quantidade recebida >= 0
            models.CheckConstraint(
                check=models.Q(quantity_received__gte=0),
                name="receiptline_quantity_received_nonnegative",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "product", "receipt"]),
        ]

    def __str__(self) -> str:
        return f"Linha {self.position} de {self.receipt_id}"
