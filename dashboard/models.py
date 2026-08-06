from django.db import models


class MonthlySummary(models.Model):
    year = models.IntegerField()
    month = models.IntegerField()
    sales_total = models.FloatField(default=0)
    expenses_total = models.FloatField(default=0)
    profit_total = models.FloatField(default=0)
    bags_sold = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('year', 'month')
        ordering = ['-year', '-month']

    def __str__(self):
        return f"{self.year}-{self.month:02d}"
from django.db import models


class DashboardMetric(models.Model):
    name = models.CharField(max_length=100)
    value = models.CharField(max_length=100)

    def __str__(self):
        return self.name
