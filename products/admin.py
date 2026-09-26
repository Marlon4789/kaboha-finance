from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'item_type', 'coffee_stage', 'base_unit',
        'is_sellable', 'is_stock_tracked', 'active',
    )
    search_fields = ('name', 'description')
    list_filter = ('item_type', 'coffee_stage', 'base_unit', 'is_sellable', 'is_stock_tracked', 'active')
    readonly_fields = ('weight_grams',)
