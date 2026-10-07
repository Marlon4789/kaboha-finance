"""Application operations that connect agricultural events with inventory."""

from datetime import datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from agriculture.models import ActivityInput, AgriculturalActivity, Harvest, ProductionBatch
from inventory.models import InventoryMovement
from inventory.services import InventoryOperationError, InventoryService
from products.models import Product


class HarvestRegistrationError(ValueError):
    """Raised when a harvest cannot be registered as an inventory receipt."""


class HarvestAlreadyRegisteredError(HarvestRegistrationError):
    """Raised when a harvest already has its unique inventory receipt."""


class ActivityInputError(ValueError):
    """Raised when an activity input cannot be recorded against inventory."""


class BatchTransformationError(ValueError):
    """Raised when a production batch cannot be posted to inventory."""


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


@transaction.atomic
def record_activity_input(activity, product, quantity, *, notes='', created_by=None, source_layers=None):
    """Record one input and consume its stock in the same transaction.

    The ActivityInput holds the declared quantity; the cost is never stored here but
    derived from the AGRICULTURAL_CONSUMPTION_OUT rows (one per FIFO or explicit layer).
    Any failure rolls back both the input and its movements. Returns (input, movements).
    """
    try:
        activity = AgriculturalActivity.objects.get(pk=getattr(activity, 'pk', activity))
        product = Product.objects.get(pk=getattr(product, 'pk', product))
    except (AgriculturalActivity.DoesNotExist, Product.DoesNotExist, TypeError, ValueError) as exc:
        raise ActivityInputError('La actividad o el producto indicado no existe.') from exc

    try:
        quantity = Decimal(str(quantity))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ActivityInputError('La cantidad del insumo debe ser un número válido.') from exc
    if not quantity.is_finite() or quantity <= 0:
        raise ActivityInputError('La cantidad del insumo debe ser mayor que cero.')

    activity_input = ActivityInput(activity=activity, product=product, quantity=quantity, notes=notes)
    try:
        activity_input.full_clean()
    except ValidationError as exc:
        raise ActivityInputError(' '.join(exc.messages)) from exc
    activity_input.save(force_insert=True)

    occurred_at = timezone.make_aware(
        datetime.combine(activity.performed_on, time.min),
        timezone.get_current_timezone(),
    )
    try:
        movements = InventoryService.consume(
            product,
            activity_input.quantity,
            movement_type=InventoryMovement.MovementType.AGRICULTURAL_CONSUMPTION_OUT,
            occurred_at=occurred_at,
            created_by=created_by,
            context={'activity_input': activity_input},
            source_layers=source_layers,
        )
    except InventoryOperationError as exc:
        raise ActivityInputError(str(exc)) from exc
    return activity_input, movements


def _coffee_gram_product(value, label):
    try:
        product = Product.objects.get(pk=getattr(value, 'pk', value))
    except (Product.DoesNotExist, TypeError, ValueError) as exc:
        raise BatchTransformationError(f'{label}: el producto indicado no existe.') from exc
    if product.item_type != Product.ItemType.COFFEE or product.base_unit != Product.BaseUnit.G:
        raise BatchTransformationError(f'{label}: debe ser café con unidad base en gramos.')
    return product


def _positive_decimal(value, label):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BatchTransformationError(f'{label} debe ser un número válido.') from exc
    if not number.is_finite() or number <= 0:
        raise BatchTransformationError(f'{label} debe ser mayor que cero.')
    return number


@transaction.atomic
def register_batch_transformation(batch, inputs, output_product, output_quantity, *, created_by=None):
    """Post one ProductionBatch as TRANSFORMATION_OUT rows plus one TRANSFORMATION_IN layer.

    `inputs` is a list of {'product', 'quantity', optional 'source_layers'} in grams.
    The new layer's unit_cost is the cost of the consumed layers divided by the output
    grams, or None when any consumed layer has no cost. Processing labor and supplies are
    not included yet. Output may not exceed input mass. Returns (outputs, incoming).
    """
    try:
        batch = ProductionBatch.objects.select_for_update().get(pk=getattr(batch, 'pk', batch))
    except (ProductionBatch.DoesNotExist, TypeError, ValueError) as exc:
        raise BatchTransformationError('El lote de producción indicado no existe.') from exc
    if InventoryMovement.objects.filter(production_batch=batch).exists():
        raise BatchTransformationError('Este lote de producción ya tiene movimientos de inventario.')
    if not inputs:
        raise BatchTransformationError('Indica al menos un café de entrada.')

    output_product = _coffee_gram_product(output_product, 'Producto de salida')
    output_quantity = _positive_decimal(output_quantity, 'La cantidad de salida')
    lines = []
    for position, line in enumerate(inputs, start=1):
        lines.append((
            _coffee_gram_product(line.get('product'), f'Entrada {position}'),
            _positive_decimal(line.get('quantity'), f'La cantidad de la entrada {position}'),
            line.get('source_layers'),
        ))
    if output_quantity > sum((quantity for _, quantity, _ in lines), Decimal('0')):
        raise BatchTransformationError('La cantidad de salida no puede superar la cantidad de entrada.')

    consumed_cost = Decimal('0')
    cost_known = True
    # Same product-pk order everywhere avoids lock inversion between concurrent batches.
    for product, quantity, source_layers in sorted(lines, key=lambda line: line[0].pk):
        try:
            rows = InventoryService.consume(
                product,
                quantity,
                movement_type=InventoryMovement.MovementType.TRANSFORMATION_OUT,
                occurred_at=batch.started_at,
                created_by=created_by,
                context={'production_batch': batch},
                source_layers=source_layers,
            )
        except InventoryOperationError as exc:
            raise BatchTransformationError(str(exc)) from exc
        for row in rows:
            if row.unit_cost is None:
                cost_known = False
            else:
                consumed_cost += row.quantity * row.unit_cost

    unit_cost = None
    if cost_known:
        unit_cost = (consumed_cost / output_quantity).quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)
    try:
        incoming = InventoryService.record_incoming(
            output_product,
            output_quantity,
            movement_type=InventoryMovement.MovementType.TRANSFORMATION_IN,
            occurred_at=batch.finished_at or batch.started_at,
            unit_cost=unit_cost,
            created_by=created_by,
            context={'production_batch': batch},
        )
    except InventoryOperationError as exc:
        raise BatchTransformationError(str(exc)) from exc
    return list(InventoryMovement.objects.filter(
        production_batch=batch, movement_type=InventoryMovement.MovementType.TRANSFORMATION_OUT,
    ).order_by('pk')), incoming
