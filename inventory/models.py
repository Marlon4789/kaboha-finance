from django.db import models
from django.utils import timezone


class InventoryEntry(models.Model):
    date = models.DateField(default=timezone.localdate)
    bags_added = models.PositiveIntegerField(default=0)
    kilos_added = models.FloatField(default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Entrada de inventario'
        verbose_name_plural = 'Entradas de inventario'

    def __str__(self):
        return f'{self.date}: +{self.bags_added} bolsas / +{self.kilos_added:.2f} kg'
