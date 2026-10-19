"""Serializers para o catálogo (ADR 0021, fatia 2; ADR 0022).

Leitura e escrita em classes separadas, campos listados um a um.
Sem `fields = "__all__"` (CLAUDE.md, SECURITY.md §4).

Convenções herdadas da fatia 1:
- `XInSerializer` / `XOutSerializer` (não `XCreateSerializer`/`XReadSerializer`)
- `Decimal` como string
- Nenhum `ModelSerializer` aqui: serialização manual permite controlar
  exactamente o que sai
"""

from __future__ import annotations

from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.catalog.ean import ean_valido
from apps.catalog.models import (
    Conservacao,
    RotuloDeValidade,
    UnidadeBase,
)
from apps.catalog.nif import nif_valido

__all__ = [
    "CodigoDeFornecedorOutSerializer",
    "EmbalagemInSerializer",
    "EmbalagemOutSerializer",
    "FornecedorInSerializer",
    "FornecedorOutSerializer",
    "FornecedorPatchInSerializer",
    "ProdutoInSerializer",
    "ProdutoOutSerializer",
    "ProdutoPatchInSerializer",
]


class EmbalagemInSerializer(serializers.Serializer):
    """Embalagem nova (aninhada em `ProdutoInSerializer`)."""

    label = serializers.CharField(
        max_length=60,
        min_length=1,
        help_text="Rótulo único por artigo (sem caixa)",
    )
    base_quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
        help_text="Unidades base por embalagem",
    )
    ean = serializers.CharField(
        max_length=14,
        required=False,
        allow_null=True,
        allow_blank=True,
        default="",
        help_text="8, 12, 13 ou 14 dígitos com dígito de controlo",
    )

    def validate_ean(self, value):
        """EAN: 8, 12, 13 ou 14 dígitos com dígito de controlo."""
        if not value:  # "" ou None
            return ""
        if not ean_valido(value):
            raise serializers.ValidationError(
                _("Invalid EAN: must be 8, 12, 13 or 14 digits with check digit.")
            )
        return value


class EmbalagemOutSerializer(serializers.Serializer):
    """Embalagem lida (aninhada em `ProdutoOutSerializer` e devolvida em GET)."""

    id = serializers.UUIDField(read_only=True)
    product = serializers.UUIDField(source="product_id", read_only=True)
    label = serializers.CharField(read_only=True)
    base_quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True
    )
    base_unit = serializers.CharField(read_only=True, source="product.base_unit")
    ean = serializers.CharField(read_only=True, allow_blank=True)


class ProdutoInSerializer(serializers.Serializer):
    """Produto novo com embalagem opcional aninhada."""

    short_name = serializers.CharField(
        max_length=80,
        min_length=1,
        help_text="Nome único por tenant (sem caixa)",
    )
    sku = serializers.CharField(
        max_length=80,
        min_length=1,
        required=False,
        allow_blank=True,
        help_text="SKU único por tenant (código de referência)",
    )
    base_unit = serializers.ChoiceField(
        choices=UnidadeBase.choices,
        help_text="g, ml ou un",
    )
    display_unit = serializers.CharField(
        max_length=20,
        min_length=1,
        help_text="Unidade de apresentação (p.ex. kg)",
    )
    display_factor = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
        help_text="Unidades base por unidade de apresentação",
    )
    track_lots = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Se exige lote",
    )
    expiry_kind = serializers.ChoiceField(
        choices=[("", "Sem rótulo")] + RotuloDeValidade.choices,
        required=False,
        allow_null=True,
        allow_blank=True,
        default="",
        help_text="use_by ou best_before",
    )
    conservation = serializers.ChoiceField(
        choices=Conservacao.choices,
        required=False,
        default=Conservacao.AMBIENT,
        help_text="ambient, chilled ou frozen",
    )
    packaging = EmbalagemInSerializer(
        required=False,
        allow_null=True,
        help_text="Primeira embalagem (opcional)",
    )

    def validate_display_factor(self, value):
        """Validar que o factor é positivo."""
        if value <= 0:
            raise serializers.ValidationError(
                _("Display factor must be positive.")
            )
        return value

    def validate_expiry_kind(self, value):
        """Normalizar: "" ou None → ""."""
        if value is None:
            return ""
        return value


class ProdutoOutSerializer(serializers.Serializer):
    """Produto lido (GET, POST 201, PATCH 200)."""

    id = serializers.UUIDField(read_only=True)
    short_name = serializers.CharField(read_only=True)
    sku = serializers.CharField(read_only=True)
    base_unit = serializers.CharField(read_only=True)
    display_unit = serializers.CharField(read_only=True)
    display_factor = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True
    )
    track_lots = serializers.BooleanField(read_only=True)
    expiry_kind = serializers.CharField(read_only=True, allow_blank=True)
    conservation = serializers.CharField(read_only=True)
    min_quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True
    )
    is_active = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class ProdutoPatchInSerializer(serializers.Serializer):
    """Produto PATCH: só os campos editáveis (sem base_unit, sem min_quantity)."""

    short_name = serializers.CharField(
        max_length=80,
        min_length=1,
        required=False,
    )
    sku = serializers.CharField(
        max_length=80,
        min_length=1,
        required=False,
    )
    display_unit = serializers.CharField(
        max_length=20,
        min_length=1,
        required=False,
    )
    display_factor = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        required=False,
    )
    track_lots = serializers.BooleanField(required=False)
    expiry_kind = serializers.ChoiceField(
        choices=[("", "Sem rótulo")] + RotuloDeValidade.choices,
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    conservation = serializers.ChoiceField(
        choices=Conservacao.choices,
        required=False,
    )
    is_active = serializers.BooleanField(required=False)

    def validate_display_factor(self, value):
        """Se presente, validar que é positivo."""
        if value is not None and value <= 0:
            raise serializers.ValidationError(
                _("Display factor must be positive.")
            )
        return value

    def validate_expiry_kind(self, value):
        """Normalizar: None → ""."""
        if value is None:
            return ""
        return value


class FornecedorInSerializer(serializers.Serializer):
    """Fornecedor novo."""

    name = serializers.CharField(
        max_length=200,
        min_length=1,
        help_text="Nome único por tenant (sem caixa)",
    )
    nif = serializers.CharField(
        max_length=9,
        required=False,
        allow_null=True,
        allow_blank=True,
        default="",
        help_text="9 dígitos com dígito de controlo",
    )

    def validate_nif(self, value):
        """NIF: 9 dígitos com dígito de controlo válido."""
        if not value:  # "" ou None
            return ""
        if not nif_valido(value):
            raise serializers.ValidationError(
                _("Invalid NIF: must be 9 digits with valid check digit.")
            )
        return value


class FornecedorOutSerializer(serializers.Serializer):
    """Fornecedor lido (GET, POST 201)."""

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    nif = serializers.CharField(read_only=True, allow_blank=True)
    is_active = serializers.BooleanField(read_only=True)


class FornecedorPatchInSerializer(serializers.Serializer):
    """Fornecedor PATCH."""

    name = serializers.CharField(
        max_length=200,
        min_length=1,
        required=False,
    )
    nif = serializers.CharField(
        max_length=9,
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    is_active = serializers.BooleanField(required=False)

    def validate_nif(self, value):
        """NIF: 9 dígitos com dígito de controlo válido."""
        if value is None or not value:
            return ""
        if not nif_valido(value):
            raise serializers.ValidationError(
                _("Invalid NIF: must be 9 digits with valid check digit.")
            )
        return value


class CodigoDeFornecedorOutSerializer(serializers.Serializer):
    """Código de fornecedor (memória, só leitura).

    GET /suppliers/{id}/product-codes — devolver `supplier_code.learned_at` e
    nome do artigo/embalagem do que se aprendeu.
    """

    code = serializers.CharField(read_only=True)
    description_raw = serializers.CharField(read_only=True, allow_blank=True)
    product = serializers.UUIDField(source="product_id", read_only=True)
    product_name = serializers.CharField(
        source="product.short_name", read_only=True
    )
    packaging = serializers.UUIDField(
        source="packaging_id", read_only=True, allow_null=True
    )
    packaging_label = serializers.CharField(
        source="packaging.label",
        read_only=True,
        allow_null=True,
    )
    learned_at = serializers.DateTimeField(read_only=True)
