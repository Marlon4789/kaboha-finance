from django.contrib import admin

from .models import (
    AgriculturalActivity, ActivityInput, ActivityLabor, CropCycle, Farm, Harvest, Lot,
    HealthObservation, ProductionBatch, QualityAssessment, Task,
)


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


@admin.register(AgriculturalActivity)
class AgriculturalActivityAdmin(admin.ModelAdmin):
    list_display = ('crop_cycle', 'activity_type', 'performed_on', 'responsible')
    list_filter = ('activity_type', 'performed_on')
    search_fields = ('notes', 'crop_cycle__lot__code', 'crop_cycle__lot__farm__name')


@admin.register(ActivityInput)
class ActivityInputAdmin(admin.ModelAdmin):
    list_display = ('activity', 'product', 'quantity', 'created_at')
    list_filter = ('product',)
    search_fields = ('product__name', 'notes')


@admin.register(ActivityLabor)
class ActivityLaborAdmin(admin.ModelAdmin):
    list_display = ('activity', 'performed_by', 'worker_name', 'hours', 'hourly_rate')
    list_filter = ('performed_by',)
    search_fields = ('worker_name', 'notes')


@admin.register(Harvest)
class HarvestAdmin(admin.ModelAdmin):
    list_display = ('crop_cycle', 'harvested_on', 'created_at')
    list_filter = ('harvested_on',)
    search_fields = ('crop_cycle__lot__code', 'crop_cycle__lot__farm__name', 'notes')


@admin.register(ProductionBatch)
class ProductionBatchAdmin(admin.ModelAdmin):
    list_display = ('code', 'process_type', 'started_at', 'finished_at', 'created_by')
    list_filter = ('process_type', 'started_at')
    search_fields = ('code', 'notes')


@admin.register(QualityAssessment)
class QualityAssessmentAdmin(admin.ModelAdmin):
    list_display = ('production_batch', 'assessed_on', 'moisture_pct', 'defects_pct', 'broca_pct', 'score')
    list_filter = ('assessed_on',)
    search_fields = ('production_batch__code', 'notes')


@admin.register(HealthObservation)
class HealthObservationAdmin(admin.ModelAdmin):
    list_display = ('crop_cycle', 'observed_on', 'problem', 'severity', 'next_review_on', 'created_by')
    list_filter = ('severity', 'observed_on')
    search_fields = ('problem', 'observation', 'action_taken', 'crop_cycle__lot__farm__name')


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'priority', 'due_on', 'assigned_to', 'created_by')
    list_filter = ('status', 'priority', 'due_on')
    search_fields = ('title', 'description')
