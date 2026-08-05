from django.contrib import admin
from django.urls import path, include
from dashboard.views import home

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='dashboard_home'),
    path('products/', include('products.urls')),
    path('sales/', include('sales.urls')),
    path('expenses/', include('expenses.urls')),
]
