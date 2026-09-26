from django.contrib import admin

from .models import CropCycle, Farm, Lot


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'municipality', 'total_area_ha', 'active')
    list_filter = ('active', 'department')
    search_fields = ('name', 'code', 'municipality', 'owner__username')


@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'farm', 'area_ha', 'current_tree_count', 'status')
    list_filter = ('status', 'farm')
    search_fields = ('code', 'name', 'farm__name')


@admin.register(CropCycle)
class CropCycleAdmin(admin.ModelAdmin):
    list_display = ('lot', 'cycle_type', 'start_date', 'end_date', 'planted_tree_count')
    list_filter = ('cycle_type', 'start_date')
    search_fields = ('lot__code', 'lot__name', 'lot__farm__name')
