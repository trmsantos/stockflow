"""URLs para relatórios."""

from django.urls import path

from apps.reporting import views

urlpatterns = [
    path("month", views.monthly_view, name="monthly-report"),
    path("series", views.series_view, name="series-report"),
    path("projection", views.projection_view, name="projection-report"),
]
