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
    operation_key = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['operation_key'],
                condition=Q(operation_key__isnull=False),
                name='sales_sale_operation_key_unique_when_set',
            ),
        ]

    def has_inventory_movements(self):
        return self.pk is not None and self.items.filter(
            inventory_movements__movement_type='SALE_OUT',
        ).exists()

    def _assert_inventory_date_is_immutable(self):
        if not self.pk:
            return
        previous_date = type(self).objects.filter(pk=self.pk).values_list('sale_date', flat=True).first()
        if previous_date != self.sale_date and self.has_inventory_movements():
            raise ValidationError({
                'sale_date': 'No se puede cambiar la fecha de una venta que ya afectó inventario.',
            })

    def clean(self):
        super().clean()
        self._assert_inventory_date_is_immutable()

    def save(self, *args, **kwargs):
        self._assert_inventory_date_is_immutable()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.has_inventory_movements():
            raise ValidationError('No se puede eliminar una venta que ya afectó inventario.')
        return super().delete(*args, **kwargs)

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

    def _assert_inventory_fields_are_immutable(self):
        if not self.pk:
            return
        previous = type(self).objects.filter(pk=self.pk).values(
            'sale_id', 'product_id', 'quantity', 'unit_price', 'unit_quantity_base_snapshot',
        ).first()
        if not previous or not self.inventory_movements.filter(movement_type='SALE_OUT').exists():
            return
        changed = [
            field for field, previous_value in previous.items()
            if getattr(self, field) != previous_value
        ]
        if changed:
            raise ValidationError(
                'No se pueden cambiar los datos estructurales de un ítem que ya afectó inventario.',
            )

    def save(self, *args, **kwargs):
        self._assert_inventory_fields_are_immutable()
        if self.product_id:
            product = self.product
            if not product.is_sellable or product.sale_unit_quantity is None or product.sale_unit_quantity <= 0:
                raise ValidationError('El producto debe ser vendible y tener contenido comercial positivo.')

            # A newly created sale item always captures the current catalog
            # presentation; callers cannot inject a different initial snapshot.
            refresh_snapshot = self._state.adding
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
