"""Rotas do painel (ADR 0029, decisão 3).

O prefixo vem daqui e não do `config/urls.py`, como nos vizinhos: o
`include("apps.reporting.urls")` entra sem argumento e é este ficheiro que diz
que os caminhos são `reporting/*`. Sem barra final e sem router — são três
leituras e não um recurso REST.

Os nomes (`reporting-summary`, …) são os que um `reverse()` usa nos testes; o
`operation_id` que o cliente gerado vê está no `@extend_schema` de cada view.
"""

from django.urls import path

from apps.reporting.views import (
    FechoDoMesView,
    ResumoDoPeriodoView,
    SeriesDoPeriodoView,
)

urlpatterns = [
    path("reporting/summary", ResumoDoPeriodoView.as_view(), name="reporting-summary"),
    path("reporting/series", SeriesDoPeriodoView.as_view(), name="reporting-series"),
    path("reporting/month", FechoDoMesView.as_view(), name="reporting-month"),
]
