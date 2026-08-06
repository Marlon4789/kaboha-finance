from django.contrib import admin
from .models import MonthlySummary


@admin.register(MonthlySummary)
class MonthlySummaryAdmin(admin.ModelAdmin):
    list_display = ('year', 'month', 'sales_total', 'expenses_total', 'profit_total', 'bags_sold', 'created_at')
    list_filter = ('year', 'month')
    ordering = ('-year', '-month')
from django.contrib import admin
from .models import DashboardMetric


@admin.register(DashboardMetric)
class DashboardMetricAdmin(admin.ModelAdmin):
    list_display = ('name', 'value')
