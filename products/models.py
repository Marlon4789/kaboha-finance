from django.db import models
from django.utils import timezone


class Product(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    weight_grams = models.PositiveIntegerField()
    sale_price = models.PositiveIntegerField()
    production_cost = models.PositiveIntegerField()
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    @property
    def profit_per_unit(self):
        return self.sale_price - self.production_cost

    @property
    def margin_percentage(self):
        if self.sale_price:
            return round((self.profit_per_unit / self.sale_price) * 100, 2)
        return 0

    def __str__(self):
        return self.name
