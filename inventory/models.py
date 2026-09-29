from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class InventoryEntry(models.Model):
    date = models.DateField(default=timezone.localdate)
    bags_added = models.PositiveIntegerField(default=0)
    kilos_added = models.FloatField(default=0, help_text='Kilos molidos')
    kilos_pergamino = models.FloatField(default=0, help_text='Kilos pergamino')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Entrada de inventario'
        verbose_name_plural = 'Entradas de inventario'

    def __str__(self):
        return f'{self.date}: +{self.bags_added} bolsas / +{self.kilos_added:.2f} kg molidos / +{self.kilos_pergamino:.2f} kg pergamino'


INVENTORY_INBOUND_TYPES = (
    'PURCHASE_IN', 'HARVEST_IN', 'TRANSFORMATION_IN', 'ADJUSTMENT_IN', 'OPENING_BALANCE_IN',
)
INVENTORY_OUTBOUND_TYPES = (
    'AGRICULTURAL_CONSUMPTION_OUT', 'TRANSFORMATION_OUT', 'SALE_OUT', 'ADJUSTMENT_OUT',
)
INVENTORY_ADJUSTMENT_TYPES = ('ADJUSTMENT_IN', 'ADJUSTMENT_OUT')


class InventoryMovement(models.Model):
    class MovementType(models.TextChoices):
        PURCHASE_IN = 'PURCHASE_IN', 'Compra (entrada)'
        HARVEST_IN = 'HARVEST_IN', 'Cosecha (entrada)'
        TRANSFORMATION_IN = 'TRANSFORMATION_IN', 'Transformación (entrada)'
        ADJUSTMENT_IN = 'ADJUSTMENT_IN', 'Ajuste positivo'
        OPENING_BALANCE_IN = 'OPENING_BALANCE_IN', 'Saldo inicial'
        AGRICULTURAL_CONSUMPTION_OUT = 'AGRICULTURAL_CONSUMPTION_OUT', 'Consumo agrícola (salida)'
        TRANSFORMATION_OUT = 'TRANSFORMATION_OUT', 'Transformación (salida)'
        SALE_OUT = 'SALE_OUT', 'Venta (salida)'
        ADJUSTMENT_OUT = 'ADJUSTMENT_OUT', 'Ajuste negativo'

    INBOUND_TYPES = INVENTORY_INBOUND_TYPES
    OUTBOUND_TYPES = INVENTORY_OUTBOUND_TYPES
    ADJUSTMENT_TYPES = INVENTORY_ADJUSTMENT_TYPES

    product = models.ForeignKey(
        'products.Product', on_delete=models.PROTECT, related_name='inventory_movements',
    )
    movement_type = models.CharField(max_length=32, choices=MovementType.choices)
    quantity = models.DecimalField(
        max_digits=18,
        decimal_places=3,
        validators=[MinValueValidator(0.001)],
    )
    occurred_at = models.DateTimeField()
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    operation_key = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Clave idempotente para operaciones excepcionales y auditables.',
    )
    expense = models.ForeignKey(
        'expenses.Expense', on_delete=models.PROTECT, related_name='inventory_movements',
        null=True, blank=True,
    )
    activity_input = models.ForeignKey(
        'agriculture.ActivityInput', on_delete=models.PROTECT, related_name='inventory_movements',
        null=True, blank=True,
    )
    harvest = models.OneToOneField(
        'agriculture.Harvest', on_delete=models.PROTECT, related_name='inventory_movement',
        null=True, blank=True,
    )
    production_batch = models.ForeignKey(
        'agriculture.ProductionBatch', on_delete=models.PROTECT, related_name='inventory_movements',
        null=True, blank=True,
    )
    sale_item = models.ForeignKey(
        'sales.SaleItem', on_delete=models.PROTECT, related_name='inventory_movements',
        null=True, blank=True,
    )
    source_movement = models.ForeignKey(
        'self', on_delete=models.PROTECT, related_name='consumptions', null=True, blank=True,
    )
    reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='created_inventory_movements', null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['occurred_at', 'pk']
        verbose_name = 'Movimiento de inventario'
        verbose_name_plural = 'Movimientos de inventario'
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name='inv_move_quantity_positive'),
            models.CheckConstraint(
                condition=Q(unit_cost__isnull=True) | Q(unit_cost__gte=0),
                name='inv_move_unit_cost_nonneg',
            ),
            models.CheckConstraint(
                condition=Q(source_movement__isnull=True) | ~Q(source_movement=F('id')),
                name='inv_move_source_not_self',
            ),
            models.CheckConstraint(
                condition=(
                    Q(movement_type__in=INVENTORY_INBOUND_TYPES, source_movement__isnull=True)
                    | Q(movement_type__in=INVENTORY_OUTBOUND_TYPES, source_movement__isnull=False)
                ),
                name='inv_move_source_by_type',
            ),
            models.CheckConstraint(
                condition=~Q(movement_type__in=INVENTORY_ADJUSTMENT_TYPES) | ~Q(reason=''),
                name='inv_move_adjustment_reason',
            ),
            models.UniqueConstraint(
                fields=['operation_key'],
                condition=Q(operation_key__isnull=False),
                name='inv_move_operation_key_unique_when_set',
            ),
        ]
        indexes = [
            models.Index(fields=['product', 'occurred_at', 'id'], name='inv_mov_product_time_idx'),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.movement_type in self.OUTBOUND_TYPES and not self.source_movement_id:
            errors['source_movement'] = 'Toda salida debe identificar la capa de inventario consumida.'
        elif self.movement_type in self.INBOUND_TYPES and self.source_movement_id:
            errors['source_movement'] = 'Una entrada no puede tener una capa fuente.'
        if self.movement_type in self.ADJUSTMENT_TYPES and not (self.reason or '').strip():
            errors['reason'] = 'Los ajustes requieren un motivo.'
        if self.pk and self.source_movement_id == self.pk:
            errors['source_movement'] = 'Un movimiento no puede ser su propia fuente.'
        if self.source_movement_id and self.product_id:
            source_product_id = type(self).objects.filter(pk=self.source_movement_id).values_list(
                'product_id', flat=True,
            ).first()
            if source_product_id is not None and source_product_id != self.product_id:
                errors['source_movement'] = 'La capa fuente debe pertenecer al mismo producto.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.get_movement_type_display()} · {self.quantity} · {self.product}'
