"""Testes para o painel/reporting (problema 6)."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import UnidadeBase
from apps.catalog.services import criar_produto
from apps.inventory.models import Location, StockMovement
from apps.reporting.services import (
    monthly_report,
    projection_report,
    series_report,
)


@pytest.mark.django_db
class TestMonthlyReport:
    """Relatório mensal."""

    def test_monthly_report_empty(self, tenant_uuid):
        """Relatório vazio para mês sem movimentos."""
        report = monthly_report(tenant_id=tenant_uuid, month="2026-10")
        assert report["period"] == "2026-10"
        assert report["revenue"] == Decimal("0")
        assert report["cogs"] == Decimal("0")
        assert len(report["items"]) == 0

    def test_monthly_report_invalid_month(self, tenant_uuid):
        """Formato de mês inválido retorna erro."""
        report = monthly_report(tenant_id=tenant_uuid, month="invalid")
        assert "error" in report

    def test_monthly_report_with_production(self, tenant_uuid, tenant_ctx):
        """Relatório com movimentos de produção."""
        # Criar produto
        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Pão",
            base_unit=UnidadeBase.GRAMA,
            display_unit="kg",
            display_factor=Decimal("1000"),
        )

        # Criar localização
        loc = Location.objects.create(
            tenant_id=tenant_uuid, name="Padaria", position=0
        )

        # Criar movimento de produção (entrada)
        now = timezone.now()
        with tenant_ctx(tenant_uuid):
            StockMovement.objects.create(
                tenant_id=tenant_uuid,
                product=produto,
                location=loc,
                movement_type="production_in",
                quantity=Decimal("100"),
                unit_cost=Decimal("0.50"),
                occurred_at=now,
            )

        # Relatório deve incluir a receita
        month = now.strftime("%Y-%m")
        report = monthly_report(tenant_id=tenant_uuid, month=month)
        assert report["revenue"] == Decimal("50.00")  # 100 × 0.50


@pytest.mark.django_db
class TestSeriesReport:
    """Série temporal."""

    def test_series_report_empty(self, tenant_uuid):
        """Série vazia para mês sem movimentos."""
        report = series_report(
            tenant_id=tenant_uuid, granularity="day", month="2026-10"
        )
        assert report["granularity"] == "day"
        assert len(report["series"]) == 0

    def test_series_report_invalid_granularity(self, tenant_uuid):
        """Granularidade inválida retorna erro."""
        report = series_report(
            tenant_id=tenant_uuid, granularity="invalid", month="2026-10"
        )
        assert "error" in report

    def test_series_report_daily(self, tenant_uuid, tenant_ctx):
        """Série diária."""
        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Biscoito",
            base_unit=UnidadeBase.GRAMA,
            display_unit="kg",
            display_factor=Decimal("1000"),
        )
        loc = Location.objects.create(
            tenant_id=tenant_uuid, name="Prateleira", position=0
        )

        now = timezone.now()
        with tenant_ctx(tenant_uuid):
            StockMovement.objects.create(
                tenant_id=tenant_uuid,
                product=produto,
                location=loc,
                movement_type="production_in",
                quantity=Decimal("50"),
                unit_cost=Decimal("1.00"),
                occurred_at=now,
            )

        month = now.strftime("%Y-%m")
        report = series_report(
            tenant_id=tenant_uuid, granularity="day", month=month
        )
        assert len(report["series"]) >= 1
        assert report["series"][0]["revenue"] == Decimal("50.00")


@pytest.mark.django_db
class TestProjectionReport:
    """Projeção de stock."""

    def test_projection_report_empty(self, tenant_uuid):
        """Projeção vazia sem produtos."""
        report = projection_report(tenant_id=tenant_uuid)
        assert report["items"] == []

    def test_projection_report_with_product(self, tenant_uuid):
        """Projeção com produto."""
        produto = criar_produto(
            tenant_id=tenant_uuid,
            short_name="Café",
            base_unit=UnidadeBase.GRAMA,
            display_unit="kg",
            display_factor=Decimal("1000"),
            sku="CAFE001",
        )

        report = projection_report(tenant_id=tenant_uuid)
        assert len(report["items"]) >= 1
        item = next((i for i in report["items"] if i["sku"] == "CAFE001"), None)
        assert item is not None
        assert item["projected"] == Decimal("0")  # Sem movimentos


@pytest.mark.django_db
class TestReportingSerialization:
    """Validar serialização dos relatórios."""

    def test_monthly_report_serializable(self, tenant_uuid):
        """Relatório mensal é serializável."""
        from apps.reporting.serializers import MonthlyReportSerializer

        report = monthly_report(tenant_id=tenant_uuid, month="2026-10")
        serializer = MonthlyReportSerializer(report)
        assert "revenue" in serializer.data
        assert "cogs" in serializer.data
