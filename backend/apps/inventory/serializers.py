"""Serializers para o inventory (ADR 0021, fatia 2; ADR 0022).

Leitura e escrita em classes separadas, campos listados um a um.
Sem `fields = "__all__"` (CLAUDE.md, SECURITY.md §4).

Nesta fatia: apenas `Location`.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

__all__ = [
    "LocalizacaoInSerializer",
    "LocalizacaoOutSerializer",
    "LocalizacaoPatchInSerializer",
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
