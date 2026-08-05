from django.urls import path
from . import views

urlpatterns = [
    path('', views.sale_list, name='sale_list'),
    path('new/', views.sale_create, name='sale_create'),
    path('<int:pk>/edit/', views.sale_edit, name='sale_edit'),
    path('<int:pk>/delete/', views.sale_delete, name='sale_delete'),
]
