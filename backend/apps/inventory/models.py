"""O inventário: localizações, lotes, movimentos (ledger) e níveis de stock.

- `Location` (fatia 2): onde a mercadoria está
- `Lot` (fatia 3): um lote de um artigo, identificado por (tenant, product, code)
- `StockMovement` (fatia 3): o ledger, append-only, nove tipos de movimento
- `StockLevel` (fatia 3): projeção (read model) do estado: saldo + custo médio
- `ProductCost` (fatia 3): custo médio ponderado por (tenant, product, location)

Nenhum é registado no admin (ADR 0007). O ledger é append-only no Postgres
(REVOKE UPDATE, DELETE) e tem RLS (ENABLE FORCE + NULLIF pattern).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models.functions import Lower

from apps.shared.models import TenantModel

__all__ = [
    "Location",
    "Lot",
    "StockMovement",
    "StockLevel",
    "ProductCost",
    "StockCount",
    "StockCountLine",
]


class Location(TenantModel):
    """Uma loja, um armazém, uma cozinha: onde a mercadoria está.

    `position` é a ordem em que as localizações aparecem — o `GET /locations`
    ordena por ela —, e o default ao criar é o fim da lista. Não é única: duas
    com a mesma posição desempatam pelo nome, e renumerar à mão é o caso raro
    que o `PATCH` cobre.

    `is_active` e nunca `DELETE`, pela razão do artigo: as linhas de receção e,
    na fatia 3, os movimentos apontam-lhe com `RESTRICT`. Uma localização
    inactiva recusa-se como destino (`localizacao_inativa`, §4.9).
    """

    name = models.CharField(max_length=60, verbose_name="nome")
    position = models.PositiveSmallIntegerField(verbose_name="ordem")
    is_active = models.BooleanField(default=True, verbose_name="ativa")

    class Meta(TenantModel.Meta):
        verbose_name = "localização"
        verbose_name_plural = "localizações"
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "tenant", name="inventory_location_name_lower_uniq"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Lot(TenantModel):
    """Um lote de mercadoria, identificado por (tenant, product, code).

    Representado por um triplo único: tenant, product (FK) e code (char 150).
    Campos:
    - `product` FK a `catalog_product`
    - `code` char(150) — o lote impresso na embalagem ou gerado (se track_lots=False,
      um lote sintético '__<product_id>__')
    - `expires_at` DateTime null — data da validade, nulável
    - `received_at` DateTime — marca do primeiro movimento que o criou, imutável

    A chave é composta (tenant_id, product_id, code) com nulls_distinct=False
    para evitar múltiplas linhas NULL por artigo.
    """

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.RESTRICT,
        related_name="+",
        db_index=False,
        verbose_name="artigo",
    )
    code = models.CharField(max_length=150, verbose_name="código do lote")
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="validade")
    received_at = models.DateTimeField(verbose_name="data de receção")

    class Meta(TenantModel.Meta):
        verbose_name = "lote"
        verbose_name_plural = "lotes"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "product", "code"],
                name="inventory_lot_unique_by_tenant_product_code",
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(
                condition=models.Q(expires_at__isnull=False),
                fields=["tenant", "expires_at"],
                name="inv_lot_tenant_expires_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Lote {self.code} ({self.product})"


class StockMovement(TenantModel):
    """O ledger de stock: append-only. Cada linha registra uma mudança de quantidade e valor.

    Campos:
    - `movement_type` — um dos nove tipos: receipt, return, consumption, waste, adjustment,
      transfer_out, transfer_in, production_out, production_in
    - `quantity` Decimal(12,3) com sinal — positivo para entrada, negativo para saída
    - `unit_cost` Decimal(12,6) — avaliação de cada unidade, immutável
    - `cost_is_estimate` bool — se o custo é estimado (A, guia sem fatura) ou
      confirmado (B, com fatura)
    - `reason` CharField com choices enum (waste, adjustment): expired, spoiled,
      prep_loss, breakage, other; `''` quando o movimento não tem motivo
    - `reason_detail` TextField — detalhes adicionais quando reason='other'; `''` se não há
    - `reference` CharField(255) — chave de deduplicação (doc_number_normalized,
      uuid produção, id contagem); `''` quando o movimento não referencia documento
    - `production_id` UUID null — referência da produção (production_out e
      production_in partilham este id)
    - `transfer_id` UUID null — ID do par transfer_out/transfer_in
    - `occurred_at` DateTime — quando o movimento aconteceu
    - `created_by` FK User SET_NULL, `created_by_name` char(150) — quem criou o movimento

    Os três campos de texto acima são `NOT NULL` com `default=''`: ausência escreve-se `''`
    e nunca `NULL`, para não haver dois valores a significar "nada" (convenção do Django, a
    mesma que o `purchasing` segue).

    Append-only na BD: REVOKE UPDATE, DELETE; CHECK(quantity != 0).
    Índice parcial: (tenant_id, reference) WHERE reference <> ''.
    """

    MOVEMENT_TYPES = [
        ("receipt", "Receção"),
        ("return", "Devolução"),
        ("consumption", "Consumo"),
        ("waste", "Desperdício"),
        ("adjustment", "Ajuste"),
        ("transfer_out", "Transferência saída"),
        ("transfer_in", "Transferência entrada"),
        ("production_out", "Produção saída"),
        ("production_in", "Produção entrada"),
    ]

    REASON_CHOICES = [
        ("expired", "Expirado"),
        ("spoiled", "Estragado"),
        ("prep_loss", "Perda de preparação"),
        ("breakage", "Quebra"),
        ("other", "Outro"),
    ]

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.RESTRICT,
        related_name="+",
        db_index=False,
        verbose_name="artigo",
    )
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.RESTRICT,
        related_name="+",
        db_index=False,
        verbose_name="localização",
    )
    lot = models.ForeignKey(
        "inventory.Lot",
        on_delete=models.RESTRICT,
        related_name="+",
        null=True,
        blank=True,
        db_index=False,
        verbose_name="lote",
    )
    movement_type = models.CharField(
        max_length=20, choices=MOVEMENT_TYPES, verbose_name="tipo de movimento"
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, verbose_name="quantidade (com sinal)"
    )
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=6, verbose_name="custo unitário"
    )
    cost_is_estimate = models.BooleanField(
        default=False, verbose_name="custo estimado"
    )
    reason = models.CharField(
        max_length=20,
        choices=REASON_CHOICES,
        blank=True,
        default="",
        verbose_name="motivo",
    )
    reason_detail = models.TextField(
        blank=True, default="", verbose_name="detalhes do motivo"
    )
    reference = models.CharField(
        max_length=255, blank=True, default="", verbose_name="referência de documento"
    )
    production_id = models.UUIDField(
        null=True, blank=True, verbose_name="ID da produção"
    )
    transfer_id = models.UUIDField(
        null=True, blank=True, verbose_name="ID da transferência"
    )
    occurred_at = models.DateTimeField(verbose_name="data/hora do movimento")
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        db_index=False,
        verbose_name="criado por",
    )
    created_by_name = models.CharField(
        max_length=150, default="", verbose_name="nome de quem criou"
    )

    class Meta(TenantModel.Meta):
        verbose_name = "movimento de stock"
        verbose_name_plural = "movimentos de stock"
        constraints = [
            models.CheckConstraint(
                check=~models.Q(quantity=Decimal("0")),
                name="inventory_stockmovement_quantity_not_zero",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "reference"],
                name="inv_stockmv_tenant_ref_idx",
                condition=~models.Q(reference=""),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_movement_type_display()} {self.quantity} ({self.product})"


class StockLevel(TenantModel):
    """Projeção (read model) do estado: saldo + custo médio.

    Única por tenant: (product_id, location_id, lot_id) com nulls_distinct=False.
    Campos:
    - `product` FK a `catalog_product`
    - `location` FK a `inventory_location`
    - `lot` FK a `inventory_lot`, null se track_lots=False
    - `quantity` Decimal(12,3) — soma dos movimentos
    - `unit_cost` Decimal(12,6) — custo unitário médio ponderado (FEFO: o mais antigo)
    """

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.RESTRICT,
        related_name="+",
        db_index=False,
        verbose_name="artigo",
    )
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.RESTRICT,
        related_name="+",
        db_index=False,
        verbose_name="localização",
    )
    lot = models.ForeignKey(
        "inventory.Lot",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
        db_index=False,
        verbose_name="lote",
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal("0"), verbose_name="quantidade"
    )
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=6, default=Decimal("0"), verbose_name="custo unitário"
    )

    class Meta(TenantModel.Meta):
        verbose_name = "nível de stock"
        verbose_name_plural = "níveis de stock"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "product", "location", "lot"],
                name="inventory_stocklevel_unique_by_tenant_product_location_lot",
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(
                condition=~models.Q(quantity=Decimal("0")),
                fields=["tenant", "location", "product"],
                name="inv_stk_tenant_loc_prod",
            ),
            models.Index(
                condition=~models.Q(quantity=Decimal("0")),
                fields=["tenant", "product", "location"],
                name="inv_stk_tenant_prod_loc",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product} @ {self.location}: {self.quantity}"


class ProductCost(TenantModel):
    """Custo médio ponderado por (tenant, product, location).

    Rationale: um tenant pode ser rede de N filiais com preços diferentes.
    Campos:
    - `product` FK a `catalog_product`
    - `location` FK a `inventory_location`
    - `unit_cost` Decimal(12,6) — a média ponderada de todas as entradas
    """

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.RESTRICT,
        related_name="+",
        db_index=False,
        verbose_name="artigo",
    )
    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.RESTRICT,
        related_name="+",
        db_index=False,
        verbose_name="localização",
    )
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=6, default=Decimal("0"), verbose_name="custo unitário"
    )

    class Meta(TenantModel.Meta):
        verbose_name = "custo de artigo"
        verbose_name_plural = "custos de artigos"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "product", "location"],
                name="inventory_productcost_unique_by_tenant_product_location",
            ),
        ]

    def __str__(self) -> str:
        return f"Custo {self.product} @ {self.location}: {self.unit_cost}"


class StockCount(TenantModel):
    """Uma contagem de stock: lista de artigos a contar numa localização.

    Campos:
    - `location` FK a `inventory_location` — onde a contagem foi feita
    - `started_at` DateTime — quando começou
    - `closed_at` DateTime null — quando foi fechada
    - `status` CharField em ["open", "closed"] — estado da contagem
    - `created_by` FK User — quem criou
    - `closed_by` FK User null — quem fechou
    - `closing_reason` CharField(200) — a justificação com que foi fechada; `''`
      enquanto a contagem está aberta. **Obrigatória no fecho e sem limiar**
      (ADR 0030, segunda ronda de respostas do dono): o limiar de 50 € era uma
      hipótese por calibrar e o dono preferiu a disciplina de uma frase em todas
      as contagens.

    ## Uma contagem aberta por **localização**, e porque é um índice

    `UniqueConstraint(tenant, location, condition=status="open")` — um índice
    único **parcial**, e não um `filter().exists()` no serviço: dois telemóveis
    a carregar em "começar" no mesmo instante veem os dois zero abertas e
    inserem os dois (ADR 0030, decisão 2). É a base que arbitra; o serviço
    apanha o `IntegrityError` e responde 409 com o id da que já estava aberta
    **naquela localização**.

    Por localização e não por estabelecimento desde a ADR 0033, decisão 1: o que
    não pode acontecer duas vezes ao mesmo tempo são **duas correcções dos
    mesmos factos**, e o fecho escreve movimentos na localização da contagem e
    em mais nenhuma. Dois instantâneos de localizações diferentes não se cruzam
    porque não têm uma única linha de `StockLevel` em comum — o argumento da
    0030 era verdadeiro, mas só **dentro** da mesma localização. Com a ADR 0030
    a pastelaria que conta de madrugada ficava bloqueada pela contagem de
    ontem, à espera de quem a fechasse.
    """

    STATUSES = [
        ("open", "Aberta"),
        ("closed", "Fechada"),
    ]

    location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.RESTRICT,
        related_name="+",
        verbose_name="localização",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUSES,
        default="open",
        verbose_name="estado",
    )
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="iniciada em")
    closed_at = models.DateTimeField(
        null=True, blank=True, verbose_name="fechada em"
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
        verbose_name="criada por",
    )
    closed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="fechada por",
    )
    closing_reason = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="justificação do fecho",
    )

    class Meta(TenantModel.Meta):
        verbose_name = "contagem de stock"
        verbose_name_plural = "contagens de stock"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "location"],
                condition=models.Q(status="open"),
                name="inventory_stockcount_uma_aberta_por_local",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "location", "status"], name="inv_count_tenant_loc_status"
            ),
            models.Index(fields=["tenant", "status"], name="inv_count_tenant_status"),
        ]

    def __str__(self) -> str:
        return f"Contagem @ {self.location} ({self.status})"


class StockCountLine(TenantModel):
    """Uma linha da contagem: um artigo com quantidade esperada e contada.

    Campos:
    - `stock_count` FK a `StockCount`
    - `product` FK a `catalog_product`
    - `lot` FK a `inventory_lot` null — sempre `NULL` nesta fatia: a linha é por
      **artigo** e o `expected` é a soma dos lotes daquela localização (ADR 0030,
      decisão 4). A coluna fica porque contar por lote é fatia própria
    - `quantity_expected` Decimal(12,3) — o que o sistema dizia **no instante da
      última observação**, e na abertura o que dizia nesse momento
    - `quantity_counted` Decimal(12,3) null — quantidade contada; `NULL` é **por
      contar** e nunca zero (zero é "contei e não havia nada", que é diferença)
    - `zone` CharField(100) — sem fonte nesta fatia: a zona *é* a localização
      (ADR 0030, decisão 3) e ninguém escreve esta coluna
    - `counted_at` DateTime null — quando foi contada, **sempre do relógio do
      servidor**: é carga aritmética (fixa o cut-off do fecho) e nunca se
      aceita do cliente

    ## A tripla atómica, e o que o `quantity_expected` **não** é

    `quantity_expected`, `quantity_counted` e `counted_at` escrevem-se **juntos
    ou não se escrevem** (ADR 0033, adenda): uma observação é um número com uma
    hora, e o esperado é o que os livros diziam a essa hora. Numa recontagem os
    três voltam a mover-se; deixar o esperado para trás comparava o número novo
    com uma hora que já passou.

    O valor materializado na abertura continua a existir — é o esperado que o
    contador vê no ecrã — mas **não é base de cálculo**: o ajuste do fecho
    compara o contado com o que o ledger diz até ao `counted_at`, recalculado no
    fecho a partir dos `occurred_at`. É um adorno de ecrã e uma leitura
    histórica, não uma aritmética.

    Invariante: `quantity_counted IS NOT NULL ⇒ counted_at IS NOT NULL`. Sem
    hora não há cut-off, logo não há base, logo não há afirmação — e é por isso
    que uma linha por contar não gera movimento nenhum.
    - `counted_by_name` CharField(150) — o nome de quem contou, **copiado** da
      pertença como nos movimentos (`created_by_name`): sobrevive à conta ser
      apagada e nunca é o email, que qualquer colega leria depois

    ## O upsert por artigo, e porque está na base

    `UniqueConstraint(tenant, stock_count, product, lot, nulls_distinct=False)` —
    o padrão do `Lot`, e o `nulls_distinct=False` é o que o torna real: com o
    `lot` a `NULL`, sem ele cada `INSERT` seria uma linha nova. Duas pessoas a
    contar o mesmo artigo deixam **uma** linha com o último valor e o último
    autor — nunca a soma dos dois —, e repetir o mesmo `POST` depois de um
    timeout é idempotente, que é o modo de falha real de contar em pé com 3G.
    """

    stock_count = models.ForeignKey(
        "inventory.StockCount",
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="contagem",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.RESTRICT,
        related_name="+",
        verbose_name="artigo",
    )
    lot = models.ForeignKey(
        "inventory.Lot",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="lote",
    )
    quantity_expected = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name="quantidade esperada",
    )
    quantity_counted = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name="quantidade contada",
    )
    zone = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="zona",
    )
    counted_at = models.DateTimeField(
        null=True, blank=True, verbose_name="contada em"
    )
    counted_by_name = models.CharField(
        max_length=150, blank=True, default="", verbose_name="contada por"
    )

    class Meta(TenantModel.Meta):
        verbose_name = "linha de contagem"
        verbose_name_plural = "linhas de contagem"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "stock_count", "product", "lot"],
                name="inventory_stockcountline_uma_por_artigo",
                nulls_distinct=False,
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "stock_count", "product"],
                name="inv_countline_tenant_sc_prod",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product} @ Contagem {self.stock_count.pk}"
