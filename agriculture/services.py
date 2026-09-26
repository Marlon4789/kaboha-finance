"""Application operations that connect agricultural events with inventory."""

from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone

from agriculture.models import Harvest
from inventory.models import InventoryMovement
from inventory.services import InventoryOperationError, InventoryService
from products.models import Product


class HarvestRegistrationError(ValueError):
    """Raised when a harvest cannot be registered as an inventory receipt."""


class HarvestAlreadyRegisteredError(HarvestRegistrationError):
    """Raised when a harvest already has its unique inventory receipt."""


@transaction.atomic
def register_harvest_inventory(
    harvest,
    product,
    quantity_kg,
    *,
    created_by=None,
):
    """Confirm one Harvest by recording its kilogram input as cherry grams in stock.

    Harvest rows without a related InventoryMovement remain unregistered/pending.
    The Harvest row is locked before checking for an existing receipt; the one-to-one
    database relation is the final duplicate guard. No cost is inferred for harvest.
    """
    harvest_pk = getattr(harvest, 'pk', harvest)
    if harvest_pk is None:
        raise HarvestRegistrationError('La cosecha debe estar guardada antes de registrarla.')
    try:
        harvest = Harvest.objects.select_for_update().get(pk=harvest_pk)
    except (Harvest.DoesNotExist, TypeError, ValueError) as exc:
        raise HarvestRegistrationError('La cosecha indicada no existe.') from exc

    if InventoryMovement.objects.filter(harvest_id=harvest.pk).exists():
        raise HarvestAlreadyRegisteredError('Esta cosecha ya fue registrada en inventario.')

    product_pk = getattr(product, 'pk', product)
    try:
        product = Product.objects.select_for_update().get(pk=product_pk)
    except (Product.DoesNotExist, TypeError, ValueError) as exc:
        raise HarvestRegistrationError('Selecciona un producto válido de café cereza.') from exc

    if product.item_type != Product.ItemType.COFFEE or product.coffee_stage != Product.CoffeeStage.CHERRY:
        raise HarvestRegistrationError('La cosecha solo puede ingresar como café en etapa cereza.')
    if product.base_unit != Product.BaseUnit.G:
        raise HarvestRegistrationError('El producto café cereza debe usar gramos como unidad base.')
    if not product.is_stock_tracked:
        raise HarvestRegistrationError('El producto café cereza debe tener control de inventario activo.')

    try:
        quantity_kg = Decimal(str(quantity_kg))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HarvestRegistrationError('La cantidad cosechada debe ser un número válido en kg.') from exc
    if not quantity_kg.is_finite() or quantity_kg <= 0:
        raise HarvestRegistrationError('La cantidad cosechada debe ser mayor que cero.')
    quantity_grams = quantity_kg * Decimal('1000')

    occurred_at = timezone.make_aware(
        datetime.combine(harvest.harvested_on, time.min),
        timezone.get_current_timezone(),
    )
    try:
        # Keep the FK's unique constraint in a savepoint so a concurrent duplicate
        # can be translated into the same domain error without breaking this transaction.
        with transaction.atomic():
            return InventoryService.record_incoming(
                product,
                quantity_grams,
                movement_type=InventoryMovement.MovementType.HARVEST_IN,
                occurred_at=occurred_at,
                unit_cost=None,
                created_by=created_by,
                context={'harvest': harvest},
            )
    except InventoryOperationError as exc:
        raise HarvestRegistrationError(str(exc)) from exc
    except IntegrityError as exc:
        if InventoryMovement.objects.filter(harvest_id=harvest.pk).exists():
            raise HarvestAlreadyRegisteredError('Esta cosecha ya fue registrada en inventario.') from exc
        raise
