from django.db import models
from django.utils import timezone


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = 'Categorías'
        ordering = ['name']

    def __str__(self):
        return self.name


class Expense(models.Model):
    date = models.DateField(default=timezone.localdate)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT)
    description = models.TextField(blank=True)
    amount = models.PositiveIntegerField()
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'{self.category.name} - {self.amount}'
