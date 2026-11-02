"""Modelos de receitas e produção (fatia 6; ADR 0035, fatia A).

`Recipe` é a ficha técnica de um artigo acabado; `RecipeLineItem` é um
ingrediente dessa ficha.

## A ficha é por **fornada**, desde 2026-11-02 (ADR 0035, decisão 8)

Era por *uma unidade base do acabado* e passou a ser pela **fornada inteira**:
`batch_size` diz quanto acabado sai de uma execução da ficha, e as linhas
escrevem a quantidade de cada ingrediente **para essa fornada**. A razão não é
ergonomia, é perda de dados: o `quantity_per_base_unit` é `Decimal(12,3)` e
dividir pela fornada ao gravar arrasa os ingredientes pequenos, que são os
caros — 2 g de corante numa fornada de 400 dão `0,005`, e uma essência numa
fornada grande dá **`0,000`**, que desaparece do custo e do consumo.

O momento é o argumento: a tabela está **vazia em todos os ambientes**, logo
mudar o significado da coluna custa zero. Um prato sem fornada escreve-se com
`batch_size = 1` na unidade base — o modelo de ontem é o caso particular de
hoje.

**O nome da coluna `quantity_per_base_unit` ficou.** Renomeá-la era um
`RenameField` (`ALTER TABLE … RENAME COLUMN`, `ACCESS EXCLUSIVE`) que parte o
código antigo a meio de um deploy em rolling — o `produzir()` e as tools de
receitas do assistente seleccionam-na pelo nome —, e a ADR 0035 pede para mudar
o **significado** e não o nome. O significado está escrito aqui e no
`help_text`; o nome é dívida nomeada.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.db import models

from apps.shared.models import TenantModel


class Recipe(TenantModel):
    """A ficha técnica de um artigo acabado: uma fornada e os seus ingredientes.

    Campos:

    - `product` — o `Product` que sai desta ficha. É a **identidade** da ficha
      (`OneToOneField`), logo não se altera: mudar o acabado é outra ficha.
    - `batch_size` — quanto acabado sai de **uma** fornada, na unidade base do
      acabado. `> 0`, imposto por `CheckConstraint` (ADR 0035, decisão 8).
    - `yield_factor` — o rendimento do processo. Nasce a `1,000` porque a perda
      já está na fornada: *"1 kg de massa → 100 pastéis"* **já contém** a merma,
      e pôr também `0,9` conta a mesma perda duas vezes. Sem tecto de 1 — arroz
      1 kg cru → 2,7 kg cozido é caso real, e o ganho é água da torneira.
    - `is_active` — uma ficha não se apaga, arquiva-se. Foi a definição de
      mercadoria que já entrou no ledger.
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    product = models.OneToOneField(
        "catalog.Product",
        on_delete=models.RESTRICT,
        related_name="recipe",
        help_text="O artigo acabado que resulta desta receita",
    )
    is_active = models.BooleanField(default=True, help_text="Se a receita está em uso")
    batch_size = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        help_text=(
            "Quanto acabado sai de **uma fornada**, na unidade base do artigo "
            "acabado (ex: 2400 para 2,4 kg de massa). Um prato sem fornada "
            "escreve-se com 1. Deve ser > 0."
        ),
    )
    yield_factor = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=Decimal("1.000"),
        validators=[],  # Validação em services.py
        help_text=(
            "Fator de rendimento do processo. Nasce a 1,000 porque a perda já "
            "está na fornada (ADR 0035, decisão 8). Deve ser > 0, sem tecto."
        ),
    )

    class Meta(TenantModel.Meta):
        verbose_name = "receita"
        verbose_name_plural = "receitas"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["tenant_id", "product_id"]),
        ]
        constraints = [
            # A fornada é o divisor do custo por unidade: a zero o custo é uma
            # divisão por zero e a negativo é um número sem significado. A
            # validação de contrato está no serializer e esta é a rede de baixo,
            # onde nenhuma escrita futura lhe escapa.
            models.CheckConstraint(
                condition=models.Q(batch_size__gt=Decimal("0")),
                name="recipes_recipe_batch_size_positivo",
            ),
        ]

    def __str__(self) -> str:
        return f"Receita de {self.product.name}"


class RecipeLineItem(TenantModel):
    """Um ingrediente de uma ficha, na quantidade que **uma fornada** consome.

    Campos:

    - `recipe` — a ficha a que a linha pertence.
    - `ingredient_product` — o artigo que entra. É sempre um artigo do catálogo:
      não há ingrediente em texto livre, e é isso que impede o mesmo ingrediente
      de existir com dois nomes em duas fichas.
    - `quantity_per_base_unit` — a quantidade **por fornada**, na unidade base
      do ingrediente. O nome da coluna é anterior à ADR 0035 e ficou (ver o
      cabeçalho do módulo): o que mudou foi o significado.

    O `unique_together (recipe, ingredient_product)` é o que torna a
    substituição total das linhas naturalmente idempotente (ADR 0035, decisão 4)
    e o que faz "ingrediente repetido" ser 400 e não duas linhas somadas em
    silêncio.
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name="line_items",
        help_text="A receita a que este ingrediente pertence",
    )
    ingredient_product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.RESTRICT,
        related_name="used_in_recipes",
        help_text="O artigo que é ingrediente",
    )
    quantity_per_base_unit = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        help_text=(
            "Quantidade **por fornada**, na unidade base do ingrediente (ex: "
            "500 para 500 g de farinha numa fornada). Desde a ADR 0035 não é "
            "por unidade do acabado — o nome da coluna é anterior."
        ),
    )

    class Meta(TenantModel.Meta):
        verbose_name = "linha de receita"
        verbose_name_plural = "linhas de receita"
        ordering = ["recipe_id", "created_at"]
        indexes = [
            models.Index(fields=["tenant_id", "recipe_id"]),
            models.Index(fields=["tenant_id", "ingredient_product_id"]),
        ]
        # Não pode haver a mesma receita + ingrediente em dobro
        unique_together = [("recipe", "ingredient_product")]

    def __str__(self) -> str:
        qty = self.quantity_per_base_unit
        unit = self.ingredient_product.base_unit
        ing = self.ingredient_product.name
        prod = self.recipe.product.name
        return f"{qty} {unit} de {ing} em {prod}"
