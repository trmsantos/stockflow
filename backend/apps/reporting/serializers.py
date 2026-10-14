"""Serializers para relatórios."""

from __future__ import annotations

from rest_framework import serializers

__all__ = [
    "MonthlyReportSerializer",
    "SeriesReportSerializer",
    "ProjectionReportSerializer",
]


class DailyItemSerializer(serializers.Serializer):
    """Item diário no relatório mensal."""

    date = serializers.CharField()
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    cogs = serializers.DecimalField(max_digits=12, decimal_places=2)
    movement_count = serializers.IntegerField()


class MonthlyReportSerializer(serializers.Serializer):
    """Relatório mensal."""

    period = serializers.CharField()
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    cogs = serializers.DecimalField(max_digits=12, decimal_places=2)
    payroll = serializers.DecimalField(max_digits=12, decimal_places=2)
    gross_profit = serializers.DecimalField(max_digits=12, decimal_places=2)
    items = DailyItemSerializer(many=True)


class SeriesItemSerializer(serializers.Serializer):
    """Item na série temporal."""

    x = serializers.CharField()
    revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    cogs = serializers.DecimalField(max_digits=12, decimal_places=2)
    gross_profit = serializers.DecimalField(max_digits=12, decimal_places=2)


class SeriesReportSerializer(serializers.Serializer):
    """Série temporal."""

    granularity = serializers.CharField()
    period = serializers.CharField()
    series = SeriesItemSerializer(many=True)


class ProjectionItemSerializer(serializers.Serializer):
    """Item em projeção."""

    sku = serializers.CharField()
    product_name = serializers.CharField()
    projected = serializers.DecimalField(max_digits=12, decimal_places=3)
    actual = serializers.DecimalField(max_digits=12, decimal_places=3)
    variance = serializers.DecimalField(max_digits=12, decimal_places=3)


class ProjectionReportSerializer(serializers.Serializer):
    """Projeção de stock."""

    items = ProjectionItemSerializer(many=True)
