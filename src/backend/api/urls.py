# pyrefly: ignore [missing-import]
from django.urls import path
from . import views

urlpatterns = [
    path('assets/', views.get_assets, name='get_assets'),
    path('incidents/', views.get_incidents, name='get_incidents'),
    path('weather/', views.get_weather, name='get_weather'),
    path('predictions/', views.get_predictions, name='get_predictions'),
    path('maintenance-plan/', views.get_maintenance_plan, name='get_maintenance_plan'),
    path('satellite-predict/', views.get_satellite_prediction, name='get_satellite_prediction'),
    path('incidents/enriched/', views.get_incidents_enriched, name='get_incidents_enriched'),
]
