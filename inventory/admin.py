from django.contrib import admin

from .models import InventoryEntry, InventoryMovement


@admin.register(InventoryEntry)
class InventoryEntryAdmin(admin.ModelAdmin):
    list_display = ('date', 'bags_added', 'kilos_added', 'created_at')
    list_filter = ('date',)
    search_fields = ('notes',)


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = (
        'occurred_at', 'product', 'movement_type', 'quantity', 'unit_cost', 'created_by', 'created_at',
    )
    list_filter = ('movement_type', 'occurred_at')
    search_fields = ('product__name', 'reason', 'notes')
    readonly_fields = tuple(field.name for field in InventoryMovement._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
