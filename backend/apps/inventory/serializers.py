"""Serializers para o inventory (ADR 0021, fatia 2; ADR 0022; ADR 0024, fatia 4).

Leitura e escrita em classes separadas, campos listados um a um.
Sem `fields = "__all__"` (CLAUDE.md, SECURITY.md §4).
"""

from __future__ import annotations

from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

__all__ = [
    "LocalizacaoInSerializer",
    "LocalizacaoOutSerializer",
    "LocalizacaoPatchInSerializer",
    "StockSummarySerializer",
    "StockDetailSerializer",
    "AlertSerializer",
]


class LocalizacaoInSerializer(serializers.Serializer):
    """Localização nova."""

    name = serializers.CharField(
        max_length=60,
        min_length=1,
        help_text="Nome único por tenant (sem caixa)",
    )
    position = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Posição (ordem). Default: fim da lista",
    )

    def validate_position(self, value):
        """Position: positivo pequeno ou None."""
        if value is not None:
            if value < 0 or value > 32767:
                raise serializers.ValidationError(
                    _("Position must be between 0 and 32767.")
                )
        return value


class LocalizacaoOutSerializer(serializers.Serializer):
    """Localização lida (GET, POST 201, PATCH 200)."""

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    position = serializers.IntegerField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)


class LocalizacaoPatchInSerializer(serializers.Serializer):
    """Localização PATCH."""

    name = serializers.CharField(
        max_length=60,
        min_length=1,
        required=False,
    )
    position = serializers.IntegerField(required=False)
    is_active = serializers.BooleanField(required=False)

    def validate_position(self, value):
        """Position: positivo pequeno."""
        if value is not None:
            if value < 0 or value > 32767:
                raise serializers.ValidationError(
                    _("Position must be between 0 and 32767.")
                )
        return value


class StockSummarySerializer(serializers.Serializer):
    """Resumo de stock agregado por produto (painel, fatia 4)."""

    product_id = serializers.UUIDField(read_only=True)
    product_name = serializers.CharField(read_only=True)
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        read_only=True,
        help_text="Quantidade total em unidade base",
    )
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=6,
        read_only=True,
        allow_null=True,
        help_text="Custo unitário (NULL se zero)",
    )
    total_value = serializers.SerializerMethodField(read_only=True)

    def get_total_value(self, obj) -> Decimal | None:
        """Quantidade × custo unitário."""
        quantity = obj.get("total_quantity")
        unit_cost = obj.get("avg_unit_cost")
        if quantity and unit_cost:
            return quantity * unit_cost
        return None


class StockDetailSerializer(serializers.Serializer):
    """Detalhe de stock por (product, lot) ou (location, lot) (fatia 4)."""

    product_id = serializers.UUIDField(read_only=True)
    product_name = serializers.CharField(read_only=True)
    location_id = serializers.UUIDField(read_only=True, allow_null=True)
    location_name = serializers.CharField(read_only=True, allow_null=True)
    lot_code = serializers.CharField(read_only=True, allow_null=True)
    expires_at = serializers.DateTimeField(
        read_only=True,
        allow_null=True,
        help_text="Data de validade (NULL se sem data)",
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        read_only=True,
        help_text="Quantidade em unidade base",
    )
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=6,
        read_only=True,
        allow_null=True,
        help_text="Custo unitário (NULL se zero)",
    )
    total_value = serializers.SerializerMethodField(read_only=True)

    def get_total_value(self, obj) -> Decimal | None:
        """Quantidade × custo unitário."""
        quantity = obj.get("quantity") or obj.get("total_quantity")
        unit_cost = obj.get("unit_cost")
        if quantity and unit_cost:
            return quantity * unit_cost
        return None


class AlertSerializer(serializers.Serializer):
    """Alerta de stock (falta, validade a vencer, vencida) (fatia 4)."""

    alert_type = serializers.CharField(
        read_only=True,
        help_text="shortage|expiring_soon|expired",
    )
    severity = serializers.CharField(
        read_only=True,
        help_text="critical|warning|info",
    )
    product_id = serializers.UUIDField(read_only=True)
    product_name = serializers.CharField(read_only=True)
    location_id = serializers.UUIDField(read_only=True, allow_null=True)
    location_name = serializers.CharField(read_only=True, allow_null=True)
    lot_code = serializers.CharField(read_only=True, allow_null=True)
    expires_at = serializers.DateTimeField(
        read_only=True,
        allow_null=True,
        help_text="Data de validade (NULL se sem data)",
    )
