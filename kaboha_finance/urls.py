from django.contrib import admin
from django.urls import path, include
from dashboard.views import home, export_month_csv, export_month_xlsx

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='dashboard_home'),
    path('dashboard/export/<int:year>/<int:month>/', export_month_csv, name='dashboard_export_month'),
    path('products/', include('products.urls')),
    path('sales/', include('sales.urls')),
    path('expenses/', include('expenses.urls')),
    path('inventory/', include('inventory.urls')),
    path('dashboard/export/xlsx/<int:year>/<int:month>/', export_month_xlsx, name='dashboard_export_month_xlsx'),
]
