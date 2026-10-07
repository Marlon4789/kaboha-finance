from decimal import Decimal

from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone


class Product(models.Model):
    class ItemType(models.TextChoices):
        COFFEE = 'COFFEE', 'Café'
        AGRICULTURAL_INPUT = 'AGRICULTURAL_INPUT', 'Insumo agrícola'
        TOOL = 'TOOL', 'Herramienta'
        OTHER = 'OTHER', 'Otro'

    class CoffeeStage(models.TextChoices):
        CHERRY = 'CHERRY', 'Cereza'
        PARCHMENT = 'PARCHMENT', 'Pergamino'
        GREEN = 'GREEN', 'Verde'
        ROASTED = 'ROASTED', 'Tostado'
        GROUND = 'GROUND', 'Molido'

    class BaseUnit(models.TextChoices):
        G = 'G', 'Gramo'
        ML = 'ML', 'Mililitro'
        UNIT = 'UNIT', 'Unidad'

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    item_type = models.CharField(max_length=20, choices=ItemType.choices, null=True, blank=True)
    coffee_stage = models.CharField(max_length=10, choices=CoffeeStage.choices, null=True, blank=True)
    base_unit = models.CharField(max_length=4, choices=BaseUnit.choices, null=True, blank=True)
    sale_unit_quantity = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.001'))],
    )
    is_sellable = models.BooleanField(default=False)
    is_stock_tracked = models.BooleanField(default=False)
    # Legacy package weight retained while sales and reports transition to snapshots.
    weight_grams = models.PositiveIntegerField(null=True, blank=True)
    sale_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
    )
    # Historical system cost; it is not the future inventory traceability costing model.
    production_cost = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Costo histórico/transicional del sistema; no es el costeo basado en inventario y trazabilidad.',
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.CheckConstraint(
                condition=Q(sale_unit_quantity__isnull=True) | Q(sale_unit_quantity__gt=0),
                name='cafena_product_sale_qty_positive',
            ),
            models.CheckConstraint(
                condition=Q(sale_price__isnull=True) | Q(sale_price__gte=0),
                name='cafena_product_sale_price_nonnegative',
            ),
            models.CheckConstraint(
                condition=(
                    Q(item_type='COFFEE', coffee_stage__in=('CHERRY', 'PARCHMENT', 'GREEN', 'ROASTED', 'GROUND'))
                    | (Q(item_type__isnull=True) & Q(coffee_stage__isnull=True))
                    | (~Q(item_type='COFFEE') & Q(coffee_stage__isnull=True))
                ),
                name='cafena_product_coffee_stage_matches_type',
            ),
            models.CheckConstraint(
                condition=Q(is_stock_tracked=False) | Q(base_unit__in=('G', 'ML', 'UNIT')),
                name='cafena_product_tracked_has_unit',
            ),
            models.CheckConstraint(
                condition=(
                    Q(is_sellable=False)
                    | (
                        Q(sale_price__isnull=False)
                        & Q(sale_unit_quantity__gt=0)
                        & Q(base_unit__in=('G', 'ML', 'UNIT'))
                    )
                ),
                name='cafena_product_sellable_ready',
            ),
        ]

    def _validate_base_unit_history(self):
        if not self.pk:
            return
        previous_unit = type(self).objects.filter(pk=self.pk).values_list('base_unit', flat=True).first()
        if previous_unit == self.base_unit:
            return
        from sales.models import SaleItem

        has_sales = SaleItem.objects.filter(product_id=self.pk).exists()
        InventoryMovement = apps.get_model('inventory', 'InventoryMovement')
        has_inventory_movements = InventoryMovement.objects.filter(product_id=self.pk).exists()
        ActivityInput = apps.get_model('agriculture', 'ActivityInput')
        has_agricultural_inputs = ActivityInput.objects.filter(product_id=self.pk).exists()
        if has_sales or has_inventory_movements or has_agricultural_inputs:
            raise ValidationError({
                'base_unit': (
                    'No se puede cambiar la unidad base después de registrar ventas, movimientos '
                    'de inventario o insumos agrícolas; crea otro producto.'
                ),
            })

    def _validate_stock_tracking_history(self):
        if not self.pk:
            return
        previous_value = type(self).objects.filter(pk=self.pk).values_list(
            'is_stock_tracked', flat=True,
        ).first()
        if previous_value is None or previous_value == self.is_stock_tracked:
            return

        InventoryMovement = apps.get_model('inventory', 'InventoryMovement')
        if InventoryMovement.objects.filter(product_id=self.pk).exists():
            raise ValidationError({
                'is_stock_tracked': (
                    'No se puede cambiar el control de inventario después de registrar movimientos '
                    'de inventario.'
                ),
            })

    def _validate_sellable_inventory(self):
        if self.is_sellable and not self.is_stock_tracked:
            raise ValidationError({
                'is_stock_tracked': 'Un producto vendible debe controlar inventario en Cafena v1.',
            })

    def clean(self):
        super().clean()
        self._validate_base_unit_history()
        self._validate_stock_tracking_history()
        self._validate_sellable_inventory()
        if self.item_type == self.ItemType.COFFEE and not self.coffee_stage:
            raise ValidationError({'coffee_stage': 'El café debe tener una etapa.'})
        if self.item_type != self.ItemType.COFFEE and self.coffee_stage:
            raise ValidationError({'coffee_stage': 'La etapa solo corresponde a productos de café.'})
        if self.is_stock_tracked and not self.base_unit:
            raise ValidationError({'base_unit': 'Un producto con stock controlado debe tener unidad base.'})
        if self.is_sellable:
            if self.sale_price is None:
                raise ValidationError({'sale_price': 'Un producto vendible debe tener precio.'})
            if self.sale_unit_quantity is None or self.sale_unit_quantity <= 0:
                raise ValidationError({'sale_unit_quantity': 'Un producto vendible debe tener contenido comercial positivo.'})
            if not self.base_unit:
                raise ValidationError({'base_unit': 'Un producto vendible debe tener unidad base.'})

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.pk and not self._state.adding:
                # Serialize these checks with InventoryService's Product-row locks.
                type(self).objects.select_for_update().filter(pk=self.pk).values_list(
                    'pk', flat=True,
                ).first()
            # Domain changes must use instance saves; QuerySet.update() bypasses these guards.
            self._validate_base_unit_history()
            self._validate_stock_tracking_history()
            super().save(*args, **kwargs)

    @property
    def profit_per_unit(self):
        if self.sale_price is None or self.production_cost is None:
            return None
        return self.sale_price - self.production_cost

    @property
    def margin_percentage(self):
        profit = self.profit_per_unit
        if profit is None or self.sale_price is None or self.sale_price == 0:
            return None
        return round((profit / self.sale_price) * 100, 2)

    def __str__(self):
        return self.name
