from django.contrib import admin
from .models import InventoryEntry


@admin.register(InventoryEntry)
class InventoryEntryAdmin(admin.ModelAdmin):
    list_display = ('date', 'bags_added', 'kilos_added', 'created_at')
    list_filter = ('date',)
    search_fields = ('notes',)
