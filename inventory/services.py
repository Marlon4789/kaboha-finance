"""Domain operations for the append-only operational inventory ledger.

Stock and logical FIFO layers are derived from InventoryMovement; InventoryEntry
is legacy aggregate data and is intentionally excluded. All writes are append-only.
Every write locks its Product row first, which is the stable serialization point
for service operations on that product in PostgreSQL. SQLite's select_for_update
is a no-op and does not provide this row-lock guarantee. A PostgreSQL concurrency
test should race two 70-unit consumes against 100 units and verify that at most
one commits. Once this ledger is operational, backdated receipts require
controlled reconciliation; existing source allocations are never recalculated.
"""

from decimal import Decimal, InvalidOperation
from collections.abc import Mapping

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from inventory.models import InventoryMovement
from products.models import Product


ZERO_QUANTITY = Decimal('0.000')
QUANTITY_FIELD = DecimalField(max_digits=18, decimal_places=3)


class InventoryOperationError(ValueError):
    """Raised when an inventory operation violates domain input rules."""


class InsufficientStockError(InventoryOperationError):
    """Raised when a requested consumption exceeds available product stock."""

    def __init__(self, product, requested_quantity, available_quantity):
        self.product = product
        self.requested_quantity = requested_quantity
        self.available_quantity = available_quantity
        unit = product.get_base_unit_display() or product.base_unit or 'unidad base'
        super().__init__(
            f'Stock insuficiente para {product.name} ({unit}): '
            f'solicitado {requested_quantity}, disponible {available_quantity}.'
        )


class InventoryService:
    """Append-only entry, stock query, FIFO consumption, and adjustment service.

    The service exposes no update/delete operation. A correction must be appended
    as a compensating adjustment. Optional context references are explicit; this
    service does not trigger Sale, Harvest, ActivityInput, Batch, or Expense flows.
    """

    INCOMING_CONTEXTS = {
        InventoryMovement.MovementType.PURCHASE_IN: {'expense'},
        InventoryMovement.MovementType.HARVEST_IN: {'harvest'},
        InventoryMovement.MovementType.TRANSFORMATION_IN: {'production_batch'},
        InventoryMovement.MovementType.OPENING_BALANCE_IN: set(),
        InventoryMovement.MovementType.ADJUSTMENT_IN: set(),
    }
    OUTGOING_CONTEXTS = {
        InventoryMovement.MovementType.AGRICULTURAL_CONSUMPTION_OUT: {'activity_input'},
        InventoryMovement.MovementType.TRANSFORMATION_OUT: {'production_batch'},
        InventoryMovement.MovementType.SALE_OUT: {'sale_item'},
        InventoryMovement.MovementType.ADJUSTMENT_OUT: set(),
    }

    @classmethod
    def _product_pk(cls, product):
        pk = getattr(product, 'pk', product)
        if pk is None:
            raise InventoryOperationError('Se requiere un producto guardado.')
        return pk

    @classmethod
    def _get_product(cls, product, *, lock=False):
        queryset = Product.objects.select_for_update() if lock else Product.objects
        try:
            instance = queryset.get(pk=cls._product_pk(product))
        except (Product.DoesNotExist, TypeError, ValueError) as exc:
            raise InventoryOperationError('El producto indicado no existe.') from exc
        if not instance.is_stock_tracked:
            raise InventoryOperationError(f'El producto {instance.name} no controla inventario.')
        if instance.base_unit not in Product.BaseUnit.values:
            raise InventoryOperationError(f'El producto {instance.name} no tiene una unidad base válida.')
        return instance

    @staticmethod
    def _decimal_value(value, field_name, label):
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise InventoryOperationError(f'{label} debe ser un número decimal válido.') from exc
        if not parsed.is_finite():
            raise InventoryOperationError(f'{label} debe ser un número decimal finito.')
        try:
            return InventoryMovement._meta.get_field(field_name).clean(parsed, None)
        except ValidationError as exc:
            raise InventoryOperationError(' '.join(exc.messages)) from exc

    @classmethod
    def _context_values(cls, context, allowed_fields):
        if context is None:
            return {}
        if not isinstance(context, Mapping):
            raise InventoryOperationError('El contexto debe ser un mapping de referencias explícitas.')
        values = dict(context)
        invalid = set(values) - allowed_fields
        if invalid:
            names = ', '.join(sorted(invalid))
            raise InventoryOperationError(f'Referencia incompatible con el tipo de movimiento: {names}.')
        return values

    @staticmethod
    def _create_movement(**values):
        movement = InventoryMovement(**values)
        try:
            movement.full_clean()
        except ValidationError as exc:
            raise InventoryOperationError(' '.join(exc.messages)) from exc
        movement.save(force_insert=True)
        return movement

    @classmethod
    @transaction.atomic
    def record_incoming(
        cls,
        product,
        quantity,
        *,
        movement_type,
        occurred_at=None,
        unit_cost=None,
        reason='',
        notes='',
        created_by=None,
        context=None,
        operation_key=None,
    ):
        """Append one positive receipt; optional context links are explicit, never automatic."""
        if movement_type not in cls.INCOMING_CONTEXTS:
            raise InventoryOperationError('El tipo indicado no es un movimiento de entrada.')
        product = cls._get_product(product, lock=True)
        quantity = cls._decimal_value(quantity, 'quantity', 'La cantidad')
        if quantity <= 0:
            raise InventoryOperationError('La cantidad de entrada debe ser mayor que cero.')
        if unit_cost is not None:
            unit_cost = cls._decimal_value(unit_cost, 'unit_cost', 'El costo unitario')
        if movement_type in InventoryMovement.ADJUSTMENT_TYPES and not (reason or '').strip():
            raise InventoryOperationError('Los ajustes requieren un motivo.')
        context_values = cls._context_values(context, cls.INCOMING_CONTEXTS[movement_type])

        return cls._create_movement(
            product=product,
            movement_type=movement_type,
            quantity=quantity,
            occurred_at=occurred_at or timezone.now(),
            unit_cost=unit_cost,
            reason=reason,
            notes=notes,
            created_by=created_by,
            operation_key=operation_key,
            **context_values,
        )

    @classmethod
    def get_stock(cls, product):
        """Return signed operational quantity in product.base_unit; legacy entries are excluded."""
        product = cls._get_product(product)
        totals = InventoryMovement.objects.filter(product=product).aggregate(
            incoming=Sum(
                'quantity',
                filter=Q(movement_type__in=InventoryMovement.INBOUND_TYPES),
                output_field=QUANTITY_FIELD,
            ),
            outgoing=Sum(
                'quantity',
                filter=Q(movement_type__in=InventoryMovement.OUTBOUND_TYPES),
                output_field=QUANTITY_FIELD,
            ),
        )
        return (totals['incoming'] or ZERO_QUANTITY) - (totals['outgoing'] or ZERO_QUANTITY)

    @classmethod
    def _available_layers_for_product(cls, product):
        consumed_quantity = Coalesce(
            Sum('consumptions__quantity'),
            Value(ZERO_QUANTITY, output_field=QUANTITY_FIELD),
            output_field=QUANTITY_FIELD,
        )
        available_quantity = ExpressionWrapper(
            F('quantity') - F('consumed_quantity'),
            output_field=QUANTITY_FIELD,
        )
        return (
            InventoryMovement.objects.filter(
                product=product,
                movement_type__in=InventoryMovement.INBOUND_TYPES,
            )
            .annotate(consumed_quantity=consumed_quantity)
            .annotate(available_quantity=available_quantity)
            .filter(available_quantity__gt=0)
            .order_by('occurred_at', 'pk')
        )

    @classmethod
    def get_available_layers(cls, product):
        """Return FIFO-ordered logical inbound layers with derived available_quantity."""
        product = cls._get_product(product)
        return cls._available_layers_for_product(product)

    @classmethod
    @transaction.atomic
    def consume(
        cls,
        product,
        quantity,
        *,
        movement_type,
        occurred_at=None,
        reason='',
        notes='',
        created_by=None,
        context=None,
    ):
        """Consume FIFO layers atomically, writing one immutable row per source layer."""
        if movement_type not in cls.OUTGOING_CONTEXTS:
            raise InventoryOperationError('El tipo indicado no es un movimiento de salida.')
        product = cls._get_product(product, lock=True)
        quantity = cls._decimal_value(quantity, 'quantity', 'La cantidad')
        if quantity <= 0:
            raise InventoryOperationError('La cantidad de salida debe ser mayor que cero.')
        if movement_type in InventoryMovement.ADJUSTMENT_TYPES and not (reason or '').strip():
            raise InventoryOperationError('Los ajustes requieren un motivo.')
        context_values = cls._context_values(context, cls.OUTGOING_CONTEXTS[movement_type])

        layers = list(cls._available_layers_for_product(product))
        available_quantity = sum((layer.available_quantity for layer in layers), ZERO_QUANTITY)
        if available_quantity < quantity:
            raise InsufficientStockError(product, quantity, available_quantity)

        remaining = quantity
        created = []
        happened_at = occurred_at or timezone.now()
        for layer in layers:
            if remaining <= 0:
                break
            consumed = min(layer.available_quantity, remaining)
            created.append(cls._create_movement(
                product=product,
                movement_type=movement_type,
                quantity=consumed,
                occurred_at=happened_at,
                unit_cost=layer.unit_cost,
                source_movement=layer,
                reason=reason,
                notes=notes,
                created_by=created_by,
                **context_values,
            ))
            remaining -= consumed
        return created

    @classmethod
    def record_adjustment(
        cls,
        product,
        quantity,
        *,
        movement_type,
        reason,
        occurred_at=None,
        unit_cost=None,
        notes='',
        created_by=None,
    ):
        """Append a positive adjustment or consume FIFO layers for a negative one."""
        if movement_type not in InventoryMovement.ADJUSTMENT_TYPES:
            raise InventoryOperationError('El ajuste debe ser ADJUSTMENT_IN o ADJUSTMENT_OUT.')
        if not (reason or '').strip():
            raise InventoryOperationError('Los ajustes requieren un motivo.')
        if movement_type == InventoryMovement.MovementType.ADJUSTMENT_IN:
            return cls.record_incoming(
                product,
                quantity,
                movement_type=movement_type,
                occurred_at=occurred_at,
                unit_cost=unit_cost,
                reason=reason,
                notes=notes,
                created_by=created_by,
            )
        if unit_cost is not None:
            raise InventoryOperationError('El costo del ajuste negativo se hereda de sus capas FIFO.')
        return cls.consume(
            product,
            quantity,
            movement_type=movement_type,
            occurred_at=occurred_at,
            reason=reason,
            notes=notes,
            created_by=created_by,
        )
