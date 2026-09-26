from django.urls import path

from agriculture import views

urlpatterns = [
    path('harvests/', views.harvest_list, name='harvest_list'),
    path('harvests/new/', views.harvest_create, name='harvest_create'),
    path('harvests/<int:pk>/register-inventory/', views.harvest_register_inventory, name='harvest_inventory_register'),
]
