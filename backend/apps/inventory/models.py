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

__all__ = ["Location", "Lot", "StockMovement", "StockLevel", "ProductCost"]


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
    - `code` char(150) — o lote impresso na embalagem ou gerado (se track_lots=False, um lote sintético '__<product_id>__')
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
    - `cost_is_estimate` bool — se o custo é estimado (A, guia sem fatura) ou confirmado (B, com fatura)
    - `reason` CharField com choices enum (waste, adjustment): expired, spoiled, prep_loss, breakage, other
    - `reason_detail` TextField null — detalhes adicionais quando reason='other'
    - `reference` CharField(255) null — chave de deduplicação (doc_number_normalized, uuid produção, id contagem)
    - `production_id` UUID null — referência da produção (production_out e production_in partilham este id)
    - `transfer_id` UUID null — ID do par transfer_out/transfer_in
    - `occurred_at` DateTime — quando o movimento aconteceu
    - `created_by` FK User SET_NULL, `created_by_name` char(150) — quem criou o movimento

    Append-only na BD: REVOKE UPDATE, DELETE; CHECK(quantity != 0).
    Índice parcial: (tenant_id, reference) WHERE reference IS NOT NULL.
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
        null=True,
        blank=True,
        verbose_name="motivo",
    )
    reason_detail = models.TextField(
        blank=True, null=True, verbose_name="detalhes do motivo"
    )
    reference = models.CharField(
        max_length=255, null=True, blank=True, verbose_name="referência de documento"
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
                condition=models.Q(reference__isnull=False),
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
