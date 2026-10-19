"""Modelos de receitas e produção (fatia 6).

Recipe: um plano de produção com ingredientes.
RecipeLineItem: um ingrediente de uma receita com quantidade.
"""

from __future__ import annotations

from uuid import uuid4

from django.db import models

from apps.shared.models import TenantModel


class Recipe(TenantModel):
    """Uma receita de produção de um artigo acabado.

    A receita tem um produto acabado (ex: pastel de nata) e N ingredientes,
    cada um com quantidade em unidade base (kg, litros, etc).

    Campos:
    - product: FK ao Product que é o resultado da receita (artigo acabado)
    - is_active: se a receita está em uso (não pode estar eliminada)
    - yield_factor: Decimal > 0, ex: 0.9 significa 10kg de entrada dão 9kg de saída
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    product = models.OneToOneField(
        "catalog.Product",
        on_delete=models.RESTRICT,
        related_name="recipe",
        help_text="O artigo acabado que resulta desta receita",
    )
    is_active = models.BooleanField(default=True, help_text="Se a receita está em uso")
    yield_factor = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        validators=[],  # Validação em services.py
        help_text="Fator de rendimento (ex: 0.9 para 10kg → 9kg). Deve ser > 0.",
    )

    class Meta(TenantModel.Meta):
        verbose_name = "receita"
        verbose_name_plural = "receitas"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["tenant_id", "product_id"]),
        ]

    def __str__(self) -> str:
        return f"Receita de {self.product.name}"


class RecipeLineItem(TenantModel):
    """Um ingrediente numa receita.

    Cada linha tem um produto ingrediente e a quantidade de unidade base
    necessária para uma produção (de quantidade 1 do produto acabado).

    Campos:
    - recipe: FK ao Recipe
    - ingredient_product: FK ao Product que é o ingrediente
    - quantity_per_base_unit: Decimal, quantidade em unidade base (ex: 10.5 kg)
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
        help_text="Quantidade em unidade base (ex: 10 para 10kg de massa)",
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
