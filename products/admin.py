from django.contrib import admin
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'weight_grams', 'sale_price', 'production_cost', 'profit_per_unit', 'margin_percentage', 'active')
    search_fields = ('name',)
    list_filter = ('active',)
