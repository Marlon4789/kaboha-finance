from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
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
        return sum(item.grams_sold() for item in self.items.select_related('product').all())

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
    unit_quantity_base_snapshot = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(unit_quantity_base_snapshot__gt=0),
                name='sales_item_snapshot_positive',
            ),
        ]

    def clean(self):
        super().clean()
        if self.product_id and not self.product.is_sellable:
            raise ValidationError({'product': 'Solo se pueden vender productos marcados como vendibles.'})
        if self.product_id and (self.product.sale_unit_quantity is None or self.product.sale_unit_quantity <= 0):
            raise ValidationError({'product': 'El producto vendible debe tener contenido comercial.'})

    def save(self, *args, **kwargs):
        if self.product_id:
            product = self.product
            if not product.is_sellable or product.sale_unit_quantity is None or product.sale_unit_quantity <= 0:
                raise ValidationError('El producto debe ser vendible y tener contenido comercial positivo.')

            refresh_snapshot = self.unit_quantity_base_snapshot is None
            if self.pk:
                previous_product_id = type(self).objects.filter(pk=self.pk).values_list('product_id', flat=True).first()
                refresh_snapshot = refresh_snapshot or previous_product_id != self.product_id
            if refresh_snapshot:
                self.unit_quantity_base_snapshot = product.sale_unit_quantity
                if kwargs.get('update_fields') is not None:
                    kwargs['update_fields'] = set(kwargs['update_fields']) | {'unit_quantity_base_snapshot'}
        super().save(*args, **kwargs)

    def subtotal(self):
        return self.quantity * self.unit_price

    def grams_sold(self):
        if self.product.base_unit != Product.BaseUnit.G or self.unit_quantity_base_snapshot is None:
            return Decimal('0')
        return self.quantity * self.unit_quantity_base_snapshot

    def kilos_sold(self):
        return self.grams_sold() / 1000

    def __str__(self):
        return f'{self.quantity} × {self.product.name}'
