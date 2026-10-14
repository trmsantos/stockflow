"""Endpoints de painel/relatórios."""

from __future__ import annotations

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.reporting.serializers import (
    MonthlyReportSerializer,
    ProjectionReportSerializer,
    SeriesReportSerializer,
)
from apps.reporting.services import (
    monthly_report,
    projection_report,
    series_report,
)

__all__ = []


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def monthly_view(request):
    """GET /reporting/month?month=YYYY-MM"""
    month = request.query_params.get("month")
    if not month:
        return Response(
            {"error": "month parameter required (format: YYYY-MM)"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    report = monthly_report(tenant_id=request.tenant.id, month=month)
    if "error" in report:
        return Response(report, status=status.HTTP_400_BAD_REQUEST)

    serializer = MonthlyReportSerializer(report)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def series_view(request):
    """GET /reporting/series?granularity=day|week|month&month=YYYY-MM"""
    granularity = request.query_params.get("granularity", "month")
    month = request.query_params.get("month")
    if not month:
        return Response(
            {"error": "month parameter required (format: YYYY-MM)"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    report = series_report(
        tenant_id=request.tenant.id, granularity=granularity, month=month
    )
    if "error" in report:
        return Response(report, status=status.HTTP_400_BAD_REQUEST)

    serializer = SeriesReportSerializer(report)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def projection_view(request):
    """GET /reporting/projection"""
    report = projection_report(tenant_id=request.tenant.id)
    serializer = ProjectionReportSerializer(report)
    return Response(serializer.data)
