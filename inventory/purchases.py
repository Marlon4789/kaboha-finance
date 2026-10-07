"""Receive purchased stock against an existing Expense, with its real unit cost.

Expense stays the single record of the cash outflow. This module only turns (part of)
that amount into a PURCHASE_IN layer so later consumption inherits the real cost.
No Expense is created or changed, and one Expense can fund several products.
"""

from datetime import datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from expenses.models import Expense
from inventory.models import InventoryMovement
from inventory.services import InventoryOperationError, InventoryService

CENT = Decimal('0.01')
UNIT_COST_PLACES = Decimal('0.00000001')


class PurchaseReceiptError(ValueError):
    """Raised when a purchase cannot be received into inventory."""


def _allocated_amount(expense):
    rows = InventoryMovement.objects.filter(
        expense=expense,
        movement_type=InventoryMovement.MovementType.PURCHASE_IN,
    ).values_list('quantity', 'unit_cost')
    return sum((quantity * unit_cost for quantity, unit_cost in rows if unit_cost is not None), Decimal('0'))


@transaction.atomic
def receive_purchase(expense, product, quantity, *, cost=None, occurred_at=None, created_by=None, notes=''):
    """Record one PURCHASE_IN layer funded by `cost` COP of the expense.

    `cost` defaults to the part of the expense not yet allocated to other receipts.
    unit_cost = cost / quantity, in the product's base unit.
    """
    try:
        expense = Expense.objects.select_for_update().get(pk=getattr(expense, 'pk', expense))
    except (Expense.DoesNotExist, TypeError, ValueError) as exc:
        raise PurchaseReceiptError('El gasto indicado no existe.') from exc

    remaining = max(Decimal(expense.amount) - _allocated_amount(expense), Decimal('0'))
    if remaining < CENT:
        raise PurchaseReceiptError('El valor de este gasto ya fue asignado por completo a entradas de inventario.')

    try:
        quantity = Decimal(str(quantity))
        cost = remaining if cost is None else Decimal(str(cost))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PurchaseReceiptError('La cantidad y el costo deben ser números válidos.') from exc
    if not quantity.is_finite() or quantity <= 0:
        raise PurchaseReceiptError('La cantidad comprada debe ser mayor que cero.')
    if not cost.is_finite() or cost <= 0:
        raise PurchaseReceiptError('El costo asignado debe ser mayor que cero.')
    if cost > remaining + CENT:
        raise PurchaseReceiptError(
            f'El costo asignado ({cost}) supera el valor pendiente del gasto ({remaining}).',
        )

    unit_cost = (cost / quantity).quantize(UNIT_COST_PLACES, rounding=ROUND_HALF_UP)
    if unit_cost <= 0:
        raise PurchaseReceiptError('El costo unitario resultante es demasiado pequeño.')
    if occurred_at is None:
        occurred_at = timezone.make_aware(
            datetime.combine(expense.date, time.min), timezone.get_current_timezone(),
        )
    try:
        return InventoryService.record_incoming(
            product,
            quantity,
            movement_type=InventoryMovement.MovementType.PURCHASE_IN,
            occurred_at=occurred_at,
            unit_cost=unit_cost,
            notes=notes,
            created_by=created_by,
            context={'expense': expense},
        )
    except InventoryOperationError as exc:
        raise PurchaseReceiptError(str(exc)) from exc
