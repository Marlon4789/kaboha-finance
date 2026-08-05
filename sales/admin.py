from django.contrib import admin
from .models import Sale, SaleItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 1


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('sale_date', 'customer_name', 'payment_method', 'total', 'created_at')
    list_filter = ('payment_method', 'sale_date')
    search_fields = ('customer_name',)
    inlines = [SaleItemInline]


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('sale', 'product', 'quantity', 'unit_price', 'subtotal')
    list_filter = ('product',)
