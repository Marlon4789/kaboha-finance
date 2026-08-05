from django.contrib import admin
from .models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('date', 'category', 'amount', 'description', 'created_at')
    list_filter = ('category', 'date')
    search_fields = ('description',)
