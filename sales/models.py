from django.db import models
from django.utils import timezone
from products.models import Product


class Sale(models.Model):
    PAYMENT_METHODS = [
        ('Efectivo', 'Efectivo'),
        ('Nequi', 'Nequi'),
        ('Daviplata', 'Daviplata'),
        ('Transferencia', 'Transferencia'),
        ('Mercado Pago', 'Mercado Pago'),
        ('Otro', 'Otro'),
    ]

    sale_date = models.DateField(default=timezone.localdate)
    customer_name = models.CharField(max_length=200, blank=True, null=True)
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHODS)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def subtotal(self):
        return sum(item.subtotal() for item in self.items.all())

    def total(self):
        return self.subtotal()

    def quantity_units(self):
        return sum(item.quantity for item in self.items.all())

    def grams_sold(self):
        return sum(item.grams_sold() for item in self.items.all())

    def kilos_sold(self):
        return self.grams_sold() / 1000

    def __str__(self):
        if self.customer_name:
            return f'Venta {self.id} - {self.customer_name} ({self.sale_date})'
        return f'Venta {self.id} - {self.sale_date}'


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.PositiveIntegerField()

    def subtotal(self):
        return self.quantity * self.unit_price

    def grams_sold(self):
        return self.quantity * self.product.weight_grams

    def kilos_sold(self):
        return self.grams_sold() / 1000

    def __str__(self):
        return f'{self.quantity} × {self.product.name}'
