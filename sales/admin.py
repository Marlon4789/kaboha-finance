from django.contrib import admin
from .models import Sale, SaleItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.has_inventory_movements())

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.has_inventory_movements():
            return ('product', 'quantity', 'unit_price', 'unit_quantity_base_snapshot')
        return ('unit_quantity_base_snapshot',)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('sale_date', 'customer_name', 'payment_method', 'total', 'created_at')
    list_filter = ('payment_method', 'sale_date')
    search_fields = ('customer_name',)
    inlines = [SaleItemInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.has_inventory_movements())

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.has_inventory_movements():
            return ('sale_date', 'customer_name', 'payment_method', 'notes', 'operation_key', 'created_at')
        return ('operation_key', 'created_at')


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('sale', 'product', 'quantity', 'unit_price', 'subtotal')
    list_filter = ('product',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.inventory_movements.filter(movement_type='SALE_OUT').exists())

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.inventory_movements.filter(movement_type='SALE_OUT').exists():
            return ('sale', 'product', 'quantity', 'unit_price', 'unit_quantity_base_snapshot')
        return ('unit_quantity_base_snapshot',)
